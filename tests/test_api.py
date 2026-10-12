"""HTTP API behaviour with in-memory stand-ins for every external service."""

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.config import Settings
from app.graph import SupportAgent
from app.main import DAILY_CAP_MESSAGE, Services, create_app
from app.ratelimit import MemoryRequestStore, RateLimiter
from app.vectorstore import VectorStore
from tests.fakes import EchoChat, FakeEmbedder, ScriptedChat


class MemoryDB:
    def __init__(self):
        self.turns, self.escalations = [], []

    def log_turn(self, turn):
        self.turns.append(turn)

    def log_escalation(self, esc):
        self.escalations.append(esc)

    def get_document(self, dataset, doc_id):
        if (dataset, doc_id) == ("halden", "warranty-policy"):
            return {"dataset": dataset, "doc_id": doc_id, "title": "Warranty Policy",
                    "source": "docs/warranty-policy.md", "last_updated": "2026-07-14", "content": "# Warranty"}
        return None

    def ping(self):
        return True


def make_client(llm=None, per_hour=20, daily_cap=500, max_chars=500):
    settings = Settings(rate_limit_per_hour=per_hour, daily_request_cap=daily_cap, max_question_chars=max_chars,
                        web_origin="http://localhost:5173", llm_api_key="unused")
    embedder = FakeEmbedder()
    store = VectorStore(QdrantClient(":memory:"))
    chunk = {"chunk_id": "00000000-0000-0000-0000-000000000001", "dataset": "halden", "doc_id": "warranty-policy",
             "doc_title": "Warranty Policy", "section_path": "Warranty Policy > Coverage",
             "source": "docs/warranty-policy.md", "position": 0, "text": "Parts and labor: 2 years from delivery."}
    store.ensure_collection("halden", embedder.dim)
    store.upsert("halden", [chunk], embedder.embed_documents([chunk["text"]]))
    db = MemoryDB()
    agent = SupportAgent(store=store, embedder=embedder, llm=llm or EchoChat(), k=6)
    limiter = RateLimiter(MemoryRequestStore(), per_hour, daily_cap)
    services = Services(settings, db, store, embedder, agent, limiter)
    return TestClient(create_app(services)), db


def test_chat_returns_answer_with_citations_and_logs_turn():
    client, db = make_client()
    r = client.post("/chat", json={"question": "How long is the warranty?", "dataset": "halden"})
    assert r.status_code == 200
    body = r.json()
    assert body["escalated"] is False
    assert body["answer"].endswith("[1].")
    cit = body["citations"][0]
    assert set(cit) >= {"citation_id", "doc_title", "section_path", "source", "excerpt"}
    assert cit["excerpt"] == "Parts and labor: 2 years from delivery."
    assert len(db.turns) == 1 and db.turns[0]["trace_id"] == body["trace_id"]
    assert db.turns[0]["retrieved_chunk_ids"] == ["00000000-0000-0000-0000-000000000001"]
    assert db.turns[0]["ip_hash"] and "testclient" not in db.turns[0]["ip_hash"]


def test_escalation_sets_flag_and_logs_escalation():
    client, db = make_client(llm=ScriptedChat(['{"sufficient": false, "reason": "no"}']))
    r = client.post("/chat", json={"question": "What is your CEO's name?"})
    body = r.json()
    assert r.status_code == 200 and body["escalated"] is True and body["citations"] == []
    assert len(db.escalations) == 1


def test_unknown_dataset_is_400():
    client, _ = make_client()
    r = client.post("/chat", json={"question": "hi", "dataset": "nope"})
    assert r.status_code == 400 and r.json()["error"] == "unknown_dataset"


def test_question_too_long_is_400():
    client, _ = make_client(max_chars=20)
    r = client.post("/chat", json={"question": "x" * 21})
    assert r.status_code == 400 and r.json()["error"] == "question_too_long"


def test_rate_limit_returns_429():
    client, _ = make_client(per_hour=2)
    for _ in range(2):
        assert client.post("/chat", json={"question": "warranty?"}).status_code == 200
    r = client.post("/chat", json={"question": "warranty?"})
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"
    assert r.headers["retry-after"] == "3600"


def test_daily_cap_returns_clear_message():
    client, _ = make_client(daily_cap=1)
    client.post("/chat", json={"question": "warranty?"})
    r = client.post("/chat", json={"question": "warranty?"})
    assert r.status_code == 429
    assert r.json() == {"error": "daily_cap", "message": DAILY_CAP_MESSAGE}


def test_datasets_lists_configured_datasets():
    client, _ = make_client()
    body = client.get("/datasets").json()
    names = [d["name"] for d in body["datasets"]]
    assert "halden" in names and body["default"] == "halden"
    halden = next(d for d in body["datasets"] if d["name"] == "halden")
    assert len(halden["examples"]) == 3


def test_get_document():
    client, _ = make_client()
    assert client.get("/docs/halden/warranty-policy").json()["title"] == "Warranty Policy"
    assert client.get("/docs/halden/missing").status_code == 404
    assert client.get("/docs/nope/x").status_code == 400


def test_ingest_requires_token():
    client, _ = make_client()
    assert client.post("/ingest", json={"dataset": "halden"}).status_code == 403


def test_cors_allows_only_web_origin():
    client, _ = make_client()
    ok = client.options("/chat", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/chat", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


@pytest.mark.parametrize("question", ["", "   "])
def test_empty_question_rejected(question):
    client, _ = make_client()
    assert client.post("/chat", json={"question": question}).status_code in (400, 422)


def test_admin_token_skips_rate_limit_and_enables_ingest_auth():
    client, _ = make_client(per_hour=1)
    client.app.state.services.settings.admin_token = "secret-token"
    client.post("/chat", json={"question": "warranty?"})
    assert client.post("/chat", json={"question": "warranty?"}).status_code == 429
    r = client.post("/chat", json={"question": "warranty?"}, headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200
    wrong = client.post("/chat", json={"question": "warranty?"}, headers={"X-Admin-Token": "nope"})
    assert wrong.status_code == 429
