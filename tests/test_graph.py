"""Escalation branch and answer flow of the LangGraph agent, with scripted model replies."""

import pytest
from qdrant_client import QdrantClient

from app.graph import HANDOFF_MESSAGE, SupportAgent
from app.vectorstore import VectorStore
from tests.fakes import FakeEmbedder, ScriptedChat

SUFFICIENT = '{"sufficient": true, "reason": "covered"}'
INSUFFICIENT = '{"sufficient": false, "reason": "not covered"}'


@pytest.fixture
def store():
    embedder = FakeEmbedder()
    vs = VectorStore(QdrantClient(":memory:"))
    texts = [
        "Parts and labor are covered for 2 years from delivery.",
        "Sealed components are covered for 5 years, parts only.",
        "Returns are accepted within 30 days of delivery.",
    ]
    chunks = [
        {"chunk_id": f"00000000-0000-0000-0000-00000000000{i}", "dataset": "demo", "doc_id": f"doc{i}",
         "doc_title": "Policy", "section_path": f"Policy > S{i}", "source": f"docs/doc{i}.md",
         "position": 0, "text": t}
        for i, t in enumerate(texts, start=1)
    ]
    vs.ensure_collection("demo", embedder.dim)
    vs.upsert("demo", chunks, embedder.embed_documents(texts))
    return vs


def run(store, replies, k=3):
    llm = ScriptedChat(replies)
    agent = SupportAgent(store=store, embedder=FakeEmbedder(), llm=llm, k=k, max_regenerations=1)
    return agent.run(dataset="demo", persona="You are a test agent.", question="How long is the warranty?"), llm


def test_valid_answer_returns_renumbered_citations(store):
    result, llm = run(store, [SUFFICIENT, "Parts are covered for 2 years [3]. Sealed parts for 5 years [1]."])
    assert not result.escalated
    assert result.answer == "Parts are covered for 2 years [1]. Sealed parts for 5 years [2]."
    assert [c.citation_id for c in result.citations] == [1, 2]
    assert result.citations[0].excerpt == result.retrieved[2].text
    assert len(llm.calls) == 2


def test_insufficient_grade_escalates_without_answering(store):
    result, llm = run(store, [INSUFFICIENT])
    assert result.escalated
    assert result.answer == HANDOFF_MESSAGE
    assert result.citations == []
    assert "context insufficient" in result.escalation_reason
    assert len(llm.calls) == 1, "answer step must not run"


def test_model_declining_escalates(store):
    result, _ = run(store, [SUFFICIENT, "NO_ANSWER"])
    assert result.escalated
    assert result.answer == HANDOFF_MESSAGE


def test_invalid_citation_regenerates_once_then_succeeds(store):
    result, llm = run(store, [SUFFICIENT, "Covered for 2 years [9].", "Covered for 2 years [1]."])
    assert not result.escalated
    assert result.answer == "Covered for 2 years [1]."
    assert "[9]" in llm.calls[2][1] and "rejected" in llm.calls[2][1]


def test_failed_validation_twice_escalates(store):
    result, llm = run(store, [SUFFICIENT, "Covered for 2 years.", "Still no citation here."])
    assert result.escalated
    assert "citation validation failed" in result.escalation_reason
    assert len(llm.calls) == 3, "exactly one regeneration"


def test_unparseable_grade_falls_through_to_validated_answer(store):
    result, _ = run(store, ["I think so", "Covered [1]."])
    assert not result.escalated


def test_no_retrieved_chunks_escalates_without_model_calls():
    vs = VectorStore(QdrantClient(":memory:"))
    llm = ScriptedChat([])
    agent = SupportAgent(store=vs, embedder=FakeEmbedder(), llm=llm, k=3)
    result = agent.run(dataset="empty", persona="p", question="anything")
    assert result.escalated
    assert llm.calls == []


class KeywordReranker:
    """Scores a passage by whether it contains a keyword, so the test controls the final order."""

    name = "keyword"

    def __init__(self, keyword: str):
        self.keyword = keyword
        self.calls: list[int] = []

    def scores(self, query, passages):
        self.calls.append(len(passages))
        return [1.0 if self.keyword in p else 0.0 for p in passages]


def test_reranker_reorders_candidates_and_keeps_top_k(store):
    reranker = KeywordReranker("Returns")
    llm = ScriptedChat([SUFFICIENT, "Returns are accepted within 30 days [1]."])
    agent = SupportAgent(store=store, embedder=FakeEmbedder(), llm=llm, k=1, reranker=reranker, rerank_candidates=3)
    result = agent.run(dataset="demo", persona="p", question="How long is the warranty?")
    assert reranker.calls == [3], "reranker sees all candidates"
    assert [c.text for c in result.retrieved] == ["Returns are accepted within 30 days of delivery."]
    assert "Returns are accepted" in llm.calls[0][1], "only the reranked top k reaches the model"


def test_reranking_is_skipped_when_candidates_do_not_exceed_k(store):
    reranker = KeywordReranker("Returns")
    llm = ScriptedChat([SUFFICIENT, "Covered [1]."])
    agent = SupportAgent(store=store, embedder=FakeEmbedder(), llm=llm, k=3, reranker=reranker, rerank_candidates=3)
    agent.run(dataset="demo", persona="p", question="warranty")
    assert reranker.calls == []


def page_store():
    """One page split into three sections, plus an unrelated page."""
    embedder = FakeEmbedder()
    vs = VectorStore(QdrantClient(":memory:"))
    rows = [
        ("guide", 0, "Guide > Intro", "You can mount other apps."),
        ("guide", 1, "Guide > How to", "Wrap the Flask app with WSGIMiddleware and mount it."),
        ("guide", 2, "Guide > Check it", "Requests under /v1 are handled by Flask."),
        ("other", 0, "Other > Run", "Run the server with the CLI."),
    ]
    chunks = [
        {"chunk_id": f"00000000-0000-0000-0000-0000000000{i:02d}", "dataset": "demo", "doc_id": doc, "doc_title": doc,
         "section_path": path, "source": f"{doc}.md", "position": pos, "text": text}
        for i, (doc, pos, path, text) in enumerate(rows)
    ]
    vs.ensure_collection("demo", embedder.dim)
    vs.upsert("demo", chunks, embedder.embed_documents([c["text"] for c in chunks]))
    return vs


def test_best_match_stays_first_and_neighbours_follow_it():
    reranker = KeywordReranker("/v1")  # puts "Check it" first
    llm = ScriptedChat([SUFFICIENT, "Wrap it with WSGIMiddleware [3]."])
    agent = SupportAgent(store=page_store(), embedder=FakeEmbedder(), llm=llm, k=1, reranker=reranker,
                         rerank_candidates=4, neighbor_window=2, expand_top=1)
    result = agent.run(dataset="demo", persona="p", question="Flask")
    assert [c.section_path for c in result.retrieved] == ["Guide > Check it", "Guide > Intro", "Guide > How to"]
    assert result.citations[0].section_path == "Guide > How to"


def test_neighbour_expansion_never_crosses_documents_or_datasets():
    vs = page_store()
    anchor = [c for c in vs.search("demo", FakeEmbedder().embed_query("server CLI"), 4) if c.doc_id == "other"]
    assert vs.neighbors("demo", anchor, window=1) == []
    assert vs.neighbors("missing", anchor, window=1) == []
