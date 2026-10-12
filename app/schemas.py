"""Request and response models for the HTTP API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    dataset: str = "halden"
    session_id: str | None = Field(default=None, max_length=100)


class CitationOut(BaseModel):
    citation_id: int
    doc_id: str
    doc_title: str
    section_path: str
    source: str
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    escalated: bool
    trace_id: str


class ErrorResponse(BaseModel):
    error: str
    message: str


class DatasetOut(BaseModel):
    name: str
    display_name: str
    description: str
    source: str
    source_url: str | None
    license: str
    license_url: str | None
    notice: str | None
    examples: list[str]


class DatasetsResponse(BaseModel):
    default: str
    datasets: list[DatasetOut]


class DocumentOut(BaseModel):
    dataset: str
    doc_id: str
    title: str
    source: str
    last_updated: str | None
    content: str


class IngestRequest(BaseModel):
    dataset: str
    force: bool = False


class IngestResponse(BaseModel):
    dataset: str
    documents: int
    chunks: int
    changed_documents: int
    removed_documents: int
    embedded: bool


class HealthResponse(BaseModel):
    status: str
    postgres: bool
    qdrant: bool
    llm_configured: bool
    collections: dict[str, int]
