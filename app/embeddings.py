"""Embedding providers: local (fastembed on CPU) or OpenAI."""

from functools import lru_cache
from typing import Protocol

from app.config import Settings, get_settings

# Retrieval instruction recommended by the BGE model authors for short queries.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class LocalEmbedder:
    def __init__(self, model: str):
        from fastembed import TextEmbedding

        self.name = f"local:{model}"
        self._model = TextEmbedding(model_name=model)
        self._query_prefix = BGE_QUERY_PREFIX if "bge" in model.lower() else ""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([self._query_prefix + text]))).tolist()


class OpenAIEmbedder:
    def __init__(self, model: str, api_key: str):
        from openai import OpenAI

        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        self.name = f"openai:{model}"
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 256):
            resp = self._client.embeddings.create(model=self._model, input=texts[i:i + 256])
            vectors.extend(d.embedding for d in resp.data)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "local":
        return LocalEmbedder(settings.embedding_model)
    if settings.embedding_provider == "openai":
        return OpenAIEmbedder(settings.embedding_model, settings.openai_api_key)
    raise ValueError(f"unknown EMBEDDING_PROVIDER {settings.embedding_provider!r}")


@lru_cache
def get_embedder() -> Embedder:
    return build_embedder(get_settings())
