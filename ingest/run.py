"""Ingest one or all datasets into Qdrant and Postgres.

    python -m ingest.run --dataset halden          # dry run: prints chunk count and cost estimate
    python -m ingest.run --dataset all --yes       # embed and write

Ingestion is idempotent. Documents whose content has not changed are skipped,
documents that were removed from disk are deleted, and the Qdrant collection is
rebuilt if the embedding size changes.
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass

from app.config import get_settings
from app.datasets import DatasetConfig, all_datasets
from ingest.chunking import load_dataset_documents

CHARS_PER_TOKEN = 4


@dataclass
class IngestResult:
    dataset: str
    documents: int
    chunks: int
    changed_documents: int
    chunks_to_embed: int
    removed_documents: int
    estimated_tokens: int
    estimated_cost_usd: float
    embedded: bool


def ingest_dataset(
    cfg: DatasetConfig,
    *,
    embedder,
    store,
    db,
    yes: bool,
    force: bool = False,
    cost_per_million: float | None = None,
    out: Callable[[str], None] = print,
) -> IngestResult:
    cost_per_million = get_settings().embedding_cost_per_million_tokens if cost_per_million is None else cost_per_million
    docs = load_dataset_documents(cfg)
    existing = db.document_hashes(cfg.name)
    vectors_present = store.count(cfg.name) > 0

    on_disk = {d.doc_id for d in docs}
    removed = sorted(set(existing) - on_disk)
    changed = [d for d in docs if force or not vectors_present or existing.get(d.doc_id) != d.content_hash]
    to_embed = [c for d in changed for c in d.chunks]
    tokens = sum(len(c.embedding_text()) for c in to_embed) // CHARS_PER_TOKEN
    cost = tokens / 1_000_000 * cost_per_million

    result = IngestResult(
        dataset=cfg.name,
        documents=len(docs),
        chunks=sum(len(d.chunks) for d in docs),
        changed_documents=len(changed),
        chunks_to_embed=len(to_embed),
        removed_documents=len(removed),
        estimated_tokens=tokens,
        estimated_cost_usd=round(cost, 6),
        embedded=False,
    )
    out(
        f"[{cfg.name}] {result.documents} documents, {result.chunks} chunks. "
        f"To embed: {result.chunks_to_embed} chunks from {result.changed_documents} changed documents "
        f"(about {tokens:,} tokens, estimated cost ${cost:.4f} with {embedder.name}). "
        f"Documents to remove: {len(removed)}."
    )
    if not yes:
        out(f"[{cfg.name}] Dry run. Re-run with --yes to embed and write.")
        return result

    if removed:
        store.delete_docs(cfg.name, removed)
        db.delete_documents(cfg.name, removed)

    if to_embed:
        probe = embedder.embed_documents([to_embed[0].embedding_text()])[0]
        if store.ensure_collection(cfg.name, len(probe)) and len(changed) < len(docs):
            # Collection was rebuilt for a new vector size, so every document must be re-embedded.
            out(f"[{cfg.name}] Vector size changed. Re-embedding all documents.")
            return ingest_dataset(cfg, embedder=embedder, store=store, db=db, yes=True, force=True,
                                  cost_per_million=cost_per_million, out=out)

    for i, doc in enumerate(changed, 1):
        chunk_dicts = [asdict(c) for c in doc.chunks]
        vectors = embedder.embed_documents([c.embedding_text() for c in doc.chunks]) if doc.chunks else []
        store.delete_docs(cfg.name, [doc.doc_id])
        if doc.chunks:
            store.upsert(cfg.name, chunk_dicts, vectors)
        db.replace_document(
            {k: v for k, v in asdict(doc).items() if k != "chunks"},
            chunk_dicts,
            vectors,
        )
        if i % 25 == 0 or i == len(changed):
            out(f"[{cfg.name}] embedded {i}/{len(changed)} documents")

    result.embedded = True
    out(f"[{cfg.name}] Done. Qdrant collection {cfg.collection} has {store.count(cfg.name)} vectors.")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest datasets into Qdrant and Postgres.")
    parser.add_argument("--dataset", required=True, help="dataset name, or 'all'")
    parser.add_argument("--yes", action="store_true", help="embed and write (without it, only print the estimate)")
    parser.add_argument("--force", action="store_true", help="re-embed every document, even unchanged ones")
    args = parser.parse_args(argv)

    datasets = all_datasets()
    if args.dataset == "all":
        selected = list(datasets.values())
    elif args.dataset in datasets:
        selected = [datasets[args.dataset]]
    else:
        print(f"Unknown dataset {args.dataset!r}. Available: {', '.join(datasets)}", file=sys.stderr)
        return 2

    from app.db import get_db
    from app.embeddings import get_embedder
    from app.vectorstore import get_vectorstore

    embedder = get_embedder() if args.yes else _NamedOnly()
    db = get_db()
    try:
        for cfg in selected:
            if not cfg.docs_path.exists():
                print(f"[{cfg.name}] {cfg.docs_path} not found, skipping. Fetch the dataset first.", file=sys.stderr)
                continue
            ingest_dataset(cfg, embedder=embedder, store=get_vectorstore(), db=db, yes=args.yes, force=args.force)
    finally:
        db.close()
    return 0


class _NamedOnly:
    """Stand-in for a dry run so the embedding model is not loaded just to print an estimate."""

    @property
    def name(self) -> str:
        s = get_settings()
        return f"{s.embedding_provider}:{s.embedding_model}"


if __name__ == "__main__":
    sys.exit(main())
