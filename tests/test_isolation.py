"""Retrieval must never return a chunk from another dataset."""

from qdrant_client import QdrantClient

from app.vectorstore import VectorStore, collection_name
from tests.fakes import FakeEmbedder

SHARED_TEXT = "How do I reset my password? Open the account page and choose reset password."


def make_chunks(dataset: str, n: int) -> list[dict]:
    return [
        {"chunk_id": f"{i:08d}-0000-0000-0000-{abs(hash(dataset)) % 10**12:012d}", "dataset": dataset,
         "doc_id": f"{dataset}-doc{i}", "doc_title": f"{dataset} doc", "section_path": f"{dataset} > {i}",
         "source": f"{dataset}/{i}.md", "position": i, "text": f"{SHARED_TEXT} Variant {i} for {dataset}."}
        for i in range(n)
    ]


def test_search_only_returns_chunks_from_requested_dataset():
    embedder = FakeEmbedder()
    store = VectorStore(QdrantClient(":memory:"))
    for name in ("alpha", "beta"):
        chunks = make_chunks(name, 10)
        store.ensure_collection(name, embedder.dim)
        store.upsert(name, chunks, embedder.embed_documents([c["text"] for c in chunks]))

    query = embedder.embed_query(SHARED_TEXT)
    for name, other in (("alpha", "beta"), ("beta", "alpha")):
        results = store.search(name, query, k=20)
        assert len(results) == 10
        assert all(r.dataset == name for r in results)
        assert not any(r.doc_id.startswith(other) for r in results)


def test_each_dataset_has_its_own_collection():
    assert collection_name("alpha") == "docs_alpha"
    assert collection_name("alpha") != collection_name("beta")


def test_foreign_point_in_collection_is_filtered_out():
    """Even if a point from another dataset ends up in the wrong collection, search drops it."""
    embedder = FakeEmbedder()
    client = QdrantClient(":memory:")
    store = VectorStore(client)
    store.ensure_collection("alpha", embedder.dim)
    good = make_chunks("alpha", 3)
    store.upsert("alpha", good, embedder.embed_documents([c["text"] for c in good]))

    from qdrant_client.http import models as qm

    intruder = make_chunks("beta", 1)[0]
    client.upsert("docs_alpha", points=[qm.PointStruct(
        id="99999999-0000-0000-0000-000000000000", vector=embedder.embed_query(SHARED_TEXT), payload=intruder)])

    results = store.search("alpha", embedder.embed_query(SHARED_TEXT), k=10)
    assert len(results) == 3
    assert all(r.dataset == "alpha" for r in results)


def test_unknown_dataset_returns_nothing():
    store = VectorStore(QdrantClient(":memory:"))
    assert store.search("missing", FakeEmbedder().embed_query("x"), k=5) == []
