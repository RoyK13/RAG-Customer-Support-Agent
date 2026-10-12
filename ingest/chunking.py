"""Load Markdown with LlamaIndex and chunk it by section.

Each chunk keeps its heading path ("Warranty Policy > Claims > Filing a claim").
Sections longer than `max_chars` are split on paragraph boundaries. Fenced code
blocks are treated as one unit and are never split, even if a single block is
longer than `max_chars`.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser

from app.datasets import DatasetConfig
from ingest.markdown import FENCE_RE, HEADING_ATTR_RE, build_source, clean_mkdocs, first_h1, split_front_matter

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CHUNK_NAMESPACE = uuid.UUID("6f1c2c1e-6c55-4a43-9a43-2d1c3c7b9e10")


@dataclass
class Chunk:
    chunk_id: str
    dataset: str
    doc_id: str
    doc_title: str
    section_path: str
    source: str
    position: int
    text: str

    def embedding_text(self) -> str:
        return f"{self.doc_title}\n{self.section_path}\n\n{self.text}"


@dataclass
class ParsedDocument:
    dataset: str
    doc_id: str
    title: str
    source: str
    last_updated: str | None
    content: str
    content_hash: str
    chunks: list[Chunk] = field(default_factory=list)


def split_blocks(text: str) -> list[str]:
    """Split Markdown into blocks at blank lines. A fenced code block is always one block."""
    blocks: list[str] = []
    current: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = FENCE_RE.match(line)
        if fence is None:
            if marker:
                if current:
                    blocks.append("\n".join(current))
                    current = []
                fence = marker.group(1)[0] * 3
                current.append(line)
            elif not line.strip():
                if current:
                    blocks.append("\n".join(current))
                    current = []
            else:
                current.append(line)
        else:
            current.append(line)
            if marker and marker.group(1).startswith(fence) and line.strip().strip(fence[0]) == "":
                blocks.append("\n".join(current))
                current = []
                fence = None
    if current:
        blocks.append("\n".join(current))
    return [b for b in blocks if b.strip()]


def pack_blocks(blocks: list[str], max_chars: int, min_chars: int) -> list[str]:
    """Greedily pack blocks into pieces of at most max_chars. Blocks are never cut."""
    pieces: list[list[str]] = []
    size = 0
    for block in blocks:
        if pieces and size + len(block) + 2 <= max_chars:
            pieces[-1].append(block)
            size += len(block) + 2
        else:
            pieces.append([block])
            size = len(block)
    # Fold a short trailing piece back into the previous one.
    if len(pieces) > 1 and sum(len(b) for b in pieces[-1]) < min_chars:
        last = pieces.pop()
        pieces[-1].extend(last)
    return ["\n\n".join(p) for p in pieces]


def chunk_id_for(dataset: str, doc_id: str, position: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return str(uuid.uuid5(CHUNK_NAMESPACE, f"{dataset}:{doc_id}:{position}:{digest}"))


def chunk_markdown(
    body: str, *, dataset: str, doc_id: str, doc_title: str, source: str, max_chars: int, min_chars: int
) -> list[Chunk]:
    nodes = MarkdownNodeParser().get_nodes_from_documents([Document(text=body)])
    heading_stack: list[tuple[int, str]] = []
    chunks: list[Chunk] = []

    for node in nodes:
        text = node.get_content().strip()
        if not text:
            continue
        first_line, _, rest = text.partition("\n")
        heading = HEADING_RE.match(first_line)
        if heading:
            level = len(heading.group(1))
            title = HEADING_ATTR_RE.sub("", heading.group(2)).strip()
            heading_stack = [h for h in heading_stack if h[0] < level] + [(level, title)]
            content = rest.strip()
        else:
            content = text
        if not content:
            continue  # heading with no body of its own

        path_parts = [t for _, t in heading_stack]
        if not path_parts or path_parts[0] != doc_title:
            path_parts = [doc_title] + path_parts
        section_path = " > ".join(path_parts)

        for piece in pack_blocks(split_blocks(content), max_chars, min_chars):
            position = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id_for(dataset, doc_id, position, piece),
                    dataset=dataset,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section_path=section_path,
                    source=source,
                    position=position,
                    text=piece,
                )
            )
    return chunks


def parse_document(path: Path, cfg: DatasetConfig) -> ParsedDocument:
    rel = PurePosixPath(path.relative_to(cfg.docs_path).as_posix())
    doc_id = rel.with_suffix("").as_posix()
    raw = path.read_text(encoding="utf-8")
    meta, body = split_front_matter(raw)

    if cfg.markdown_flavor == "mkdocs":
        include_root = cfg.path / cfg.include_root if cfg.include_root else None
        body, _ = clean_mkdocs(body, include_root=include_root, sandbox=cfg.path)

    title = str(meta.get("title") or first_h1(body) or rel.stem.replace("-", " ").title())
    last_updated = meta.get("last_updated")
    source = build_source(rel, cfg.docs_dir, cfg.source_url.style, cfg.source_url.base_url)
    doc = ParsedDocument(
        dataset=cfg.name,
        doc_id=doc_id,
        title=title,
        source=source,
        last_updated=str(last_updated) if last_updated else None,
        content=body,
        content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )
    doc.chunks = chunk_markdown(
        body,
        dataset=cfg.name,
        doc_id=doc_id,
        doc_title=title,
        source=source,
        max_chars=cfg.chunking.max_chars,
        min_chars=cfg.chunking.min_chars,
    )
    return doc


def iter_markdown_files(cfg: DatasetConfig) -> list[Path]:
    files = sorted(cfg.docs_path.rglob("*.md"))
    excluded = set()
    for pattern in cfg.exclude:
        excluded.update(cfg.docs_path.glob(pattern))
    return [f for f in files if f not in excluded]


def load_dataset_documents(cfg: DatasetConfig) -> list[ParsedDocument]:
    if not cfg.docs_path.exists():
        raise FileNotFoundError(f"{cfg.docs_path} does not exist. Fetch the dataset first.")
    return [parse_document(f, cfg) for f in iter_markdown_files(cfg)]
