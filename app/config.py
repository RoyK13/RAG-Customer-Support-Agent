"""Application settings. Every value can be overridden with an environment variable."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Chat model. Any OpenAI-compatible endpoint works (OpenAI, Gemini, Groq, OpenRouter).
    llm_base_url: str | None = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        description="Leave empty to use the OpenAI API.",
    )
    llm_api_key: str = ""
    llm_model: str = "gemini-3.5-flash-lite"
    llm_reasoning_effort: str = "low"
    # Tried in order when the primary model is overloaded or unavailable (comma separated).
    llm_fallback_models: str = "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash"
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 60.0

    # Embeddings: "local" (fastembed, runs on CPU) or "openai".
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_api_key: str = ""
    embedding_cost_per_million_tokens: float = 0.0

    # Retrieval and answer validation
    retrieval_top_k: int = 6
    # Dense search fetches this many candidates, a cross-encoder reranks them, and the best
    # retrieval_top_k are kept. 0 disables reranking (plain dense top-k).
    rerank_candidates: int = 20
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    # Also give the model up to neighbor_window sections on each side of the top N chunks, from the
    # same document. 0 disables. Context grows to at most retrieval_top_k + 2 * window * N blocks.
    neighbor_window: int = 2
    neighbor_expand_top: int = 1
    max_regenerations: int = 1

    # Storage
    qdrant_url: str = "http://localhost:6333"
    database_url: str = "postgresql://support:support@localhost:5432/support"

    # Datasets
    data_dir: Path = ROOT_DIR / "data"
    default_dataset: str = "halden"

    # Public demo protection
    rate_limit_per_hour: int = 20
    daily_request_cap: int = 150
    max_question_chars: int = 500
    ip_hash_salt: str = "change-me"
    trust_proxy_headers: bool = False

    # Data retention, in days. 0 keeps data forever. A cleanup runs at API startup and then daily.
    log_retention_days: int = 30          # chat_turns and escalations
    request_log_retention_days: int = 2   # rate-limit log (only the last 24 hours are ever read)

    # Web app origin allowed by CORS (comma separated for more than one)
    web_origin: str = "http://localhost:5173"

    # Admin token (X-Admin-Token header): enables POST /ingest and lets the eval runner skip rate limits.
    admin_token: str = ""

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.web_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
