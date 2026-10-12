"""HTTP API for the support agent."""

import hmac
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.datasets import all_datasets, get_dataset
from app.graph import SupportAgent
from app.llm import LLMUnavailable
from app.ratelimit import RateLimiter, hash_ip
from app.schemas import (
    ChatRequest,
    ChatResponse,
    CitationOut,
    DatasetOut,
    DatasetsResponse,
    DocumentOut,
    ErrorResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s %(message)s")
log = logging.getLogger("support_agent")

DAILY_CAP_MESSAGE = "Demo limit reached, try again tomorrow."
RATE_LIMIT_MESSAGE = "You have sent too many questions in the last hour. Try again later."


@dataclass
class Services:
    settings: Settings
    db: object
    store: object
    embedder: object
    agent: SupportAgent | None
    limiter: RateLimiter


def build_services(settings: Settings) -> Services:
    from app.db import get_db
    from app.embeddings import get_embedder
    from app.llm import get_chat_model
    from app.reranker import get_reranker
    from app.vectorstore import get_vectorstore

    db = get_db()
    store = get_vectorstore()
    embedder = get_embedder()
    try:
        llm = get_chat_model()
        agent = SupportAgent(
            store=store, embedder=embedder, llm=llm, k=settings.retrieval_top_k,
            max_regenerations=settings.max_regenerations,
            reranker=get_reranker(), rerank_candidates=settings.rerank_candidates,
            neighbor_window=settings.neighbor_window, expand_top=settings.neighbor_expand_top,
        )
    except LLMUnavailable as exc:
        log.warning("chat model not configured: %s", exc)
        agent = None
    limiter = RateLimiter(db, settings.rate_limit_per_hour, settings.daily_request_cap)
    return Services(settings, db, store, embedder, agent, limiter)


def error(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(ErrorResponse(error=code, message=message).model_dump(), status_code=status, headers=headers)


def create_app(services: Services | None = None) -> FastAPI:
    settings = services.settings if services else get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # The daily retention cleanup runs only for the real app, not when tests inject services.
        stop = None
        if services is None:
            from app.db import get_db
            from app.retention import start_daily_purge

            stop = start_daily_purge(get_db, settings)
        yield
        if stop is not None:
            stop.set()

    app = FastAPI(title="Support Agent API", docs_url="/api-docs", redoc_url=None, lifespan=lifespan)
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def get_services() -> Services:
        if app.state.services is None:
            app.state.services = build_services(settings)
        return app.state.services

    def client_ip(request: Request, s: Services) -> str:
        if s.settings.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def is_admin(s: Services, token: str) -> bool:
        return bool(s.settings.admin_token) and hmac.compare_digest(s.settings.admin_token, token)

    @app.post("/chat", response_model=ChatResponse, responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
    def chat(body: ChatRequest, request: Request, s: Services = Depends(get_services),
             x_admin_token: str = Header(default="")):
        cfg = get_dataset(body.dataset)
        if cfg is None:
            return error(400, "unknown_dataset", f"Unknown dataset {body.dataset!r}. Available: {', '.join(all_datasets())}.")
        question = body.question.strip()
        if not question:
            return error(400, "empty_question", "The question is empty.")
        if len(question) > s.settings.max_question_chars:
            return error(400, "question_too_long", f"Questions can be at most {s.settings.max_question_chars} characters.")

        ip_hash = hash_ip(client_ip(request, s), s.settings.ip_hash_salt)
        decision = None if is_admin(s, x_admin_token) else s.limiter.check_and_record(ip_hash, cfg.name)
        if decision is not None and not decision.allowed:
            message = DAILY_CAP_MESSAGE if decision.reason == "daily_cap" else RATE_LIMIT_MESSAGE
            return error(429, decision.reason or "rate_limited", message, {"Retry-After": str(decision.retry_after_seconds)})

        if s.agent is None:
            return error(503, "model_unavailable", "The chat model is not configured on the server.")

        trace_id = str(uuid.uuid4())
        started = time.perf_counter()
        try:
            result = s.agent.run(dataset=cfg.name, persona=cfg.persona, question=question)
        except LLMUnavailable as exc:
            log.error("model call failed trace_id=%s: %s", trace_id, exc)
            return error(503, "model_unavailable", "The language model is not responding right now. Try again in a minute.")
        latency_ms = int((time.perf_counter() - started) * 1000)

        citations = [
            CitationOut(citation_id=c.citation_id, doc_id=c.doc_id, doc_title=c.doc_title,
                        section_path=c.section_path, source=c.source, excerpt=c.excerpt)
            for c in result.citations
        ]
        try:
            s.db.log_turn({
                "trace_id": trace_id,
                "dataset": cfg.name,
                "session_id": body.session_id,
                "question": question,
                "retrieved_chunk_ids": [c.chunk_id for c in result.retrieved],
                "answer": result.answer,
                "citations": [asdict(c) for c in result.citations],
                "escalated": result.escalated,
                "escalation_reason": result.escalation_reason,
                "latency_ms": latency_ms,
                "ip_hash": ip_hash,
            })
            if result.escalated:
                s.db.log_escalation({
                    "trace_id": trace_id, "dataset": cfg.name, "session_id": body.session_id,
                    "question": question, "reason": result.escalation_reason or "",
                })
        except Exception:  # logging must not break the answer
            log.exception("failed to log turn trace_id=%s", trace_id)

        return ChatResponse(answer=result.answer, citations=citations, escalated=result.escalated, trace_id=trace_id)

    @app.get("/datasets", response_model=DatasetsResponse)
    def datasets():
        items = [
            DatasetOut(
                name=c.name, display_name=c.display_name, description=c.description,
                source=c.source.label, source_url=c.source.url, license=c.license.name,
                license_url=c.license.url, notice=c.notice, examples=c.examples,
            )
            for c in all_datasets().values()
        ]
        return DatasetsResponse(default=settings.default_dataset, datasets=items)

    @app.get("/docs/{dataset}/{doc_id:path}", response_model=DocumentOut, responses={404: {"model": ErrorResponse}})
    def get_document(dataset: str, doc_id: str, s: Services = Depends(get_services)):
        if get_dataset(dataset) is None:
            return error(400, "unknown_dataset", f"Unknown dataset {dataset!r}.")
        doc = s.db.get_document(dataset, doc_id)
        if doc is None:
            return error(404, "not_found", "Document not found.")
        return DocumentOut(**doc)

    @app.post("/ingest", response_model=IngestResponse, responses={403: {"model": ErrorResponse}})
    def ingest(body: IngestRequest, s: Services = Depends(get_services), x_admin_token: str = Header(default="")):
        if not is_admin(s, x_admin_token):
            return error(403, "forbidden", "Ingestion requires a valid X-Admin-Token header.")
        cfg = get_dataset(body.dataset)
        if cfg is None:
            return error(400, "unknown_dataset", f"Unknown dataset {body.dataset!r}.")
        from ingest.run import ingest_dataset

        r = ingest_dataset(cfg, embedder=s.embedder, store=s.store, db=s.db, yes=True, force=body.force, out=log.info)
        return IngestResponse(dataset=r.dataset, documents=r.documents, chunks=r.chunks,
                              changed_documents=r.changed_documents, removed_documents=r.removed_documents,
                              embedded=r.embedded)

    @app.get("/health", response_model=HealthResponse)
    def health(s: Services = Depends(get_services)):
        pg_ok = qdrant_ok = False
        collections: dict[str, int] = {}
        try:
            pg_ok = s.db.ping()
        except Exception:
            log.exception("postgres health check failed")
        try:
            collections = {name: s.store.count(name) for name in all_datasets()}
            qdrant_ok = True
        except Exception:
            log.exception("qdrant health check failed")
        status = "ok" if pg_ok and qdrant_ok and s.agent is not None else "degraded"
        return HealthResponse(status=status, postgres=pg_ok, qdrant=qdrant_ok,
                              llm_configured=s.agent is not None, collections=collections)

    return app


app = create_app()
