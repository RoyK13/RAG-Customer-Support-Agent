"""Postgres access: document metadata, chunks, conversation logs, escalations, request log."""

import json
from datetime import datetime
from functools import lru_cache

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    dataset      text NOT NULL,
    doc_id       text NOT NULL,
    title        text NOT NULL,
    source       text NOT NULL,
    last_updated text,
    content      text NOT NULL,
    content_hash text NOT NULL,
    ingested_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset, doc_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     uuid PRIMARY KEY,
    dataset      text NOT NULL,
    doc_id       text NOT NULL,
    doc_title    text NOT NULL,
    section_path text NOT NULL,
    source       text NOT NULL,
    position     integer NOT NULL,
    text         text NOT NULL,
    embedding    vector,
    FOREIGN KEY (dataset, doc_id) REFERENCES documents (dataset, doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chunks_dataset_doc_idx ON chunks (dataset, doc_id);

CREATE TABLE IF NOT EXISTS chat_turns (
    id                  bigserial PRIMARY KEY,
    trace_id            uuid NOT NULL UNIQUE,
    dataset             text NOT NULL,
    session_id          text,
    question            text NOT NULL,
    retrieved_chunk_ids text[] NOT NULL,
    answer              text NOT NULL,
    citations           jsonb NOT NULL,
    escalated           boolean NOT NULL,
    escalation_reason   text,
    latency_ms          integer NOT NULL,
    ip_hash             text,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_turns_dataset_created_idx ON chat_turns (dataset, created_at);

CREATE TABLE IF NOT EXISTS escalations (
    id         bigserial PRIMARY KEY,
    trace_id   uuid NOT NULL,
    dataset    text NOT NULL,
    session_id text,
    question   text NOT NULL,
    reason     text NOT NULL,
    status     text NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS request_log (
    id         bigserial PRIMARY KEY,
    dataset    text NOT NULL,
    ip_hash    text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS request_log_ip_created_idx ON request_log (ip_hash, created_at);
CREATE INDEX IF NOT EXISTS request_log_created_idx ON request_log (created_at);
"""


class Database:
    def __init__(self, url: str):
        self.pool = ConnectionPool(url, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row})
        self._schema_ready = False

    def open(self) -> None:
        self.pool.open(wait=True, timeout=30)
        self.init_schema()

    def close(self) -> None:
        self.pool.close()

    def init_schema(self) -> None:
        if self._schema_ready:
            return
        with self.pool.connection() as conn:
            conn.execute(SCHEMA)
        self._schema_ready = True

    def ping(self) -> bool:
        with self.pool.connection() as conn:
            return conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1

    # Documents and chunks

    def document_hashes(self, dataset: str) -> dict[str, str]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT doc_id, content_hash FROM documents WHERE dataset = %s", (dataset,)).fetchall()
        return {r["doc_id"]: r["content_hash"] for r in rows}

    def replace_document(self, doc: dict, chunks: list[dict], vectors: list[list[float]]) -> None:
        import numpy as np

        with self.pool.connection() as conn:
            register_vector(conn)
            with conn.transaction():
                conn.execute("DELETE FROM documents WHERE dataset = %s AND doc_id = %s", (doc["dataset"], doc["doc_id"]))
                conn.execute(
                    """INSERT INTO documents (dataset, doc_id, title, source, last_updated, content, content_hash)
                       VALUES (%(dataset)s, %(doc_id)s, %(title)s, %(source)s, %(last_updated)s, %(content)s, %(content_hash)s)""",
                    doc,
                )
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO chunks (chunk_id, dataset, doc_id, doc_title, section_path, source, position, text, embedding)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        [
                            (c["chunk_id"], c["dataset"], c["doc_id"], c["doc_title"], c["section_path"],
                             c["source"], c["position"], c["text"], np.array(v, dtype=np.float32))
                            for c, v in zip(chunks, vectors, strict=True)
                        ],
                    )

    def delete_documents(self, dataset: str, doc_ids: list[str]) -> None:
        if not doc_ids:
            return
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM documents WHERE dataset = %s AND doc_id = ANY(%s)", (dataset, doc_ids))

    def delete_dataset(self, dataset: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM documents WHERE dataset = %s", (dataset,))

    def get_document(self, dataset: str, doc_id: str) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute(
                """SELECT dataset, doc_id, title, source, last_updated, content
                   FROM documents WHERE dataset = %s AND doc_id = %s""",
                (dataset, doc_id),
            ).fetchone()

    def get_chunks(self, chunk_ids: list[str]) -> list[dict]:
        """Chunks by ID, in the order given."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT chunk_id::text AS chunk_id, dataset, doc_id, doc_title, section_path, source, text
                   FROM chunks WHERE chunk_id = ANY(%s::uuid[])""",
                (chunk_ids,),
            ).fetchall()
        by_id = {r["chunk_id"]: r for r in rows}
        return [by_id[c] for c in chunk_ids if c in by_id]

    def chunk_count(self, dataset: str) -> int:
        with self.pool.connection() as conn:
            return conn.execute("SELECT count(*) AS n FROM chunks WHERE dataset = %s", (dataset,)).fetchone()["n"]

    # Conversation logs and escalations

    def log_turn(self, turn: dict) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO chat_turns (trace_id, dataset, session_id, question, retrieved_chunk_ids, answer,
                                           citations, escalated, escalation_reason, latency_ms, ip_hash)
                   VALUES (%(trace_id)s, %(dataset)s, %(session_id)s, %(question)s, %(retrieved_chunk_ids)s, %(answer)s,
                           %(citations)s, %(escalated)s, %(escalation_reason)s, %(latency_ms)s, %(ip_hash)s)""",
                {**turn, "citations": json.dumps(turn["citations"])},
            )

    def log_escalation(self, esc: dict) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO escalations (trace_id, dataset, session_id, question, reason)
                   VALUES (%(trace_id)s, %(dataset)s, %(session_id)s, %(question)s, %(reason)s)""",
                esc,
            )

    def get_turn(self, trace_id: str) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute("SELECT * FROM chat_turns WHERE trace_id = %s", (trace_id,)).fetchone()

    # Request log used by the rate limiter

    def count_requests(self, since: datetime, ip_hash: str | None = None) -> int:
        with self.pool.connection() as conn:
            if ip_hash is None:
                row = conn.execute("SELECT count(*) AS n FROM request_log WHERE created_at >= %s", (since,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT count(*) AS n FROM request_log WHERE ip_hash = %s AND created_at >= %s", (ip_hash, since)
                ).fetchone()
        return row["n"]

    def purge_older_than(self, log_cutoff: datetime | None, request_cutoff: datetime | None) -> dict[str, int]:
        """Delete conversation logs and escalations before log_cutoff, and rate-limit rows before
        request_cutoff. A cutoff of None keeps that data. Returns rows deleted per table."""
        deleted = {"chat_turns": 0, "escalations": 0, "request_log": 0}
        with self.pool.connection() as conn, conn.transaction():
            if log_cutoff is not None:
                for table in ("chat_turns", "escalations"):
                    deleted[table] = conn.execute(f"DELETE FROM {table} WHERE created_at < %s", (log_cutoff,)).rowcount
            if request_cutoff is not None:
                deleted["request_log"] = conn.execute(
                    "DELETE FROM request_log WHERE created_at < %s", (request_cutoff,)
                ).rowcount
        return deleted

    def record_request(self, dataset: str, ip_hash: str, at: datetime) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO request_log (dataset, ip_hash, created_at) VALUES (%s, %s, %s)", (dataset, ip_hash, at)
            )


@lru_cache
def get_db() -> Database:
    db = Database(get_settings().database_url)
    db.open()
    return db
