"""Integration test: ingest the halden dataset into the Docker Qdrant and Postgres, then call /chat.

Run with the services up:
    docker compose up -d qdrant postgres
    pytest -m integration

Uses a separate test dataset name and collection so it never touches real data.
Embeddings use the configured provider (local fastembed by default). The chat
model is a deterministic stand-in so the test is free and reproducible; set
RUN_LLM_TESTS=1 to use the real model from .env instead.
"""

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.datasets import load_dataset
from app.db import Database
from app.graph import SupportAgent
from app.main import Services, create_app
from app.ratelimit import RateLimiter
from app.vectorstore import VectorStore
from ingest.run import ingest_dataset
from tests.fakes import EchoChat

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
TEST_DATASET = "halden_itest"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    settings = get_settings()
    try:
        from qdrant_client import QdrantClient

        qclient = QdrantClient(url=settings.qdrant_url, timeout=5)
        qclient.get_collections()
        db = Database(settings.database_url)
        db.open()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Docker services not reachable: {exc}")

    # Copy halden under a test name so the real collection and rows are untouched.
    data_dir = tmp_path_factory.mktemp("data")
    shutil.copytree(ROOT / "data" / "halden", data_dir / TEST_DATASET)
    yaml_path = data_dir / TEST_DATASET / "dataset.yaml"
    yaml_path.write_text(yaml_path.read_text(encoding="utf-8").replace("name: halden", f"name: {TEST_DATASET}"),
                         encoding="utf-8")
    cfg = load_dataset(data_dir / TEST_DATASET)

    from app.embeddings import get_embedder

    store = VectorStore(qclient)
    embedder = get_embedder()
    yield {"cfg": cfg, "db": db, "store": store, "embedder": embedder, "settings": settings, "data_dir": data_dir}

    if qclient.collection_exists(f"docs_{TEST_DATASET}"):
        qclient.delete_collection(f"docs_{TEST_DATASET}")
    db.delete_dataset(TEST_DATASET)
    with db.pool.connection() as conn:
        for table in ("chat_turns", "escalations", "request_log"):
            conn.execute(f"DELETE FROM {table} WHERE dataset = %s", (TEST_DATASET,))
    db.close()


def test_ingest_then_chat(env, monkeypatch):
    cfg, db, store, embedder = env["cfg"], env["db"], env["store"], env["embedder"]
    db.delete_dataset(TEST_DATASET)

    first = ingest_dataset(cfg, embedder=embedder, store=store, db=db, yes=True, out=lambda _: None)
    assert first.embedded and first.chunks > 100
    assert store.count(TEST_DATASET) == first.chunks
    assert db.chunk_count(TEST_DATASET) == first.chunks

    again = ingest_dataset(cfg, embedder=embedder, store=store, db=db, yes=True, out=lambda _: None)
    assert again.chunks_to_embed == 0, "re-ingesting unchanged documents must be a no-op"
    assert store.count(TEST_DATASET) == first.chunks

    # Point the dataset registry at the temporary data dir.
    from app import datasets as registry

    monkeypatch.setattr(registry, "get_dataset", lambda name: cfg if name == TEST_DATASET else None)
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "get_dataset", lambda name: cfg if name == TEST_DATASET else None)

    if os.environ.get("RUN_LLM_TESTS") == "1":
        from app.llm import get_chat_model
        llm = get_chat_model()
    else:
        llm = EchoChat()
    settings = env["settings"]
    agent = SupportAgent(store=store, embedder=embedder, llm=llm, k=settings.retrieval_top_k)
    services = Services(settings, db, store, embedder, agent, RateLimiter(db, 1000, 0))
    client = TestClient(create_app(services))

    r = client.post("/chat", json={"question": "How long is the warranty on the dishwasher pump motor?",
                                   "dataset": TEST_DATASET})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["citations"], body
    assert all(c["section_path"] for c in body["citations"])
    retrieved_titles = {c["doc_title"] for c in body["citations"]}
    assert "Warranty Policy" in retrieved_titles

    turn = db.get_turn(body["trace_id"])
    assert turn is not None and turn["dataset"] == TEST_DATASET
    assert len(turn["retrieved_chunk_ids"]) == settings.retrieval_top_k


def test_retention_deletes_only_old_rows(env):
    from datetime import UTC, datetime, timedelta

    db = env["db"]
    now = datetime.now(UTC)
    with db.pool.connection() as conn:
        for age_days in (40, 1):
            conn.execute(
                """INSERT INTO chat_turns (trace_id, dataset, question, retrieved_chunk_ids, answer, citations,
                                           escalated, latency_ms, created_at)
                   VALUES (gen_random_uuid(), %s, 'q', '{}', 'a', '[]', false, 1, %s)""",
                (TEST_DATASET, now - timedelta(days=age_days)),
            )
            conn.execute("INSERT INTO request_log (dataset, ip_hash, created_at) VALUES (%s, 'x', %s)",
                         (TEST_DATASET, now - timedelta(days=age_days * 3)))
    deleted = db.purge_older_than(now - timedelta(days=30), now - timedelta(days=2))
    assert deleted["chat_turns"] >= 1 and deleted["request_log"] >= 1
    with db.pool.connection() as conn:
        left = conn.execute("SELECT count(*) AS n FROM chat_turns WHERE dataset = %s", (TEST_DATASET,)).fetchone()["n"]
        old_req = conn.execute("SELECT count(*) AS n FROM request_log WHERE dataset = %s AND created_at < %s",
                               (TEST_DATASET, now - timedelta(days=2))).fetchone()["n"]
    assert left >= 1, "recent turns are kept"
    assert old_req == 0, "rate-limit rows older than the cutoff are gone"
