"""Cross-encoder reranking of retrieved chunks (fastembed, runs locally on CPU)."""

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class Reranker(Protocol):
    name: str

    def scores(self, query: str, passages: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Reads each (question, passage) pair together, so it weighs specific terms such as
    product or library names that a small embedding model can miss."""

    def __init__(self, model: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = model
        self._model = TextCrossEncoder(model_name=model)

    def scores(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, passages, batch_size=32)]


@lru_cache
def get_reranker() -> Reranker | None:
    s = get_settings()
    if s.rerank_candidates <= 0 or not s.reranker_model:
        return None
    return CrossEncoderReranker(s.reranker_model)
