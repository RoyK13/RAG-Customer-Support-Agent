"""Qdrant access. Each dataset has its own collection, named docs_<dataset>."""

from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import get_settings


@dataclass
class RetrievedChunk:
    chunk_id: str
    dataset: str
    doc_id: str
    doc_title: str
    section_path: str
    source: str
    position: int
    text: str
    score: float


def collection_name(dataset: str) -> str:
    return f"docs_{dataset}"


class VectorStore:
    def __init__(self, client: QdrantClient):
        self.client = client

    def collection_dim(self, dataset: str) -> int | None:
        name = collection_name(dataset)
        if not self.client.collection_exists(name):
            return None
        params = self.client.get_collection(name).config.params.vectors
        return params.size  # type: ignore[union-attr]

    def ensure_collection(self, dataset: str, dim: int) -> bool:
        """Create the collection, or recreate it if the vector size changed. Returns True if (re)created."""
        name = collection_name(dataset)
        current = self.collection_dim(dataset)
        if current == dim:
            return False
        if current is not None:
            self.client.delete_collection(name)
        self.client.create_collection(name, vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE))
        self.client.create_payload_index(name, "dataset", qm.PayloadSchemaType.KEYWORD)
        self.client.create_payload_index(name, "doc_id", qm.PayloadSchemaType.KEYWORD)
        return True

    def upsert(self, dataset: str, chunks: list[dict], vectors: list[list[float]]) -> None:
        points = [
            qm.PointStruct(id=c["chunk_id"], vector=v, payload={**c, "dataset": dataset})
            for c, v in zip(chunks, vectors, strict=True)
        ]
        for i in range(0, len(points), 256):
            self.client.upsert(collection_name(dataset), points=points[i:i + 256], wait=True)

    def delete_docs(self, dataset: str, doc_ids: list[str]) -> None:
        if not doc_ids or self.collection_dim(dataset) is None:
            return
        self.client.delete(
            collection_name(dataset),
            points_selector=qm.FilterSelector(
                filter=qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=doc_ids))])
            ),
            wait=True,
        )

    def count(self, dataset: str) -> int:
        if self.collection_dim(dataset) is None:
            return 0
        return self.client.count(collection_name(dataset), exact=True).count

    def neighbors(self, dataset: str, anchors: list[RetrievedChunk], window: int = 1) -> list[RetrievedChunk]:
        """Chunks within `window` positions of each anchor in the same document, excluding the anchors."""
        if not anchors or window <= 0 or self.collection_dim(dataset) is None:
            return []
        near = [
            qm.Filter(must=[
                qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=a.doc_id)),
                qm.FieldCondition(key="position", range=qm.Range(gte=a.position - window, lte=a.position + window)),
            ])
            for a in anchors
        ]
        points, _ = self.client.scroll(
            collection_name(dataset),
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="dataset", match=qm.MatchValue(value=dataset))], should=near
            ),
            limit=len(anchors) * (2 * window + 1),
            with_payload=True,
        )
        anchor_ids = {a.chunk_id for a in anchors}
        return [
            self._to_chunk(p.payload or {}, 0.0)
            for p in points
            if (p.payload or {}).get("dataset") == dataset and str((p.payload or {}).get("chunk_id")) not in anchor_ids
        ]

    @staticmethod
    def _to_chunk(p: dict, score: float) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=str(p["chunk_id"]),
            dataset=p["dataset"],
            doc_id=p["doc_id"],
            doc_title=p["doc_title"],
            section_path=p["section_path"],
            source=p["source"],
            position=int(p["position"]),
            text=p["text"],
            score=score,
        )

    def search(self, dataset: str, vector: list[float], k: int) -> list[RetrievedChunk]:
        """Dense search inside one dataset's collection, also filtered on the dataset payload."""
        if self.collection_dim(dataset) is None:
            return []
        hits = self.client.query_points(
            collection_name(dataset),
            query=vector,
            limit=k,
            with_payload=True,
            query_filter=qm.Filter(must=[qm.FieldCondition(key="dataset", match=qm.MatchValue(value=dataset))]),
        ).points
        results = []
        for hit in hits:
            p = hit.payload or {}
            if p.get("dataset") != dataset:  # defensive: never leak another dataset's chunk
                continue
            results.append(self._to_chunk(p, float(hit.score)))
        return results


@lru_cache
def get_vectorstore() -> VectorStore:
    return VectorStore(QdrantClient(url=get_settings().qdrant_url, timeout=30))
