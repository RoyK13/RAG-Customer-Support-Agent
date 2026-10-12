"""Grader models for evaluation: a cached, quota-aware client plus adapters for Ragas and DeepEval.

Every grader reply is cached on disk, so an interrupted run (for example when a
free-tier daily quota runs out) resumes without repeating calls.
"""

import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError  # noqa: E402

from app.llm import parse_json_object, rate_limit_info  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / ".cache"


class QuotaExhausted(RuntimeError):
    """Every configured grader model has used up its quota."""


def is_daily_quota_error(exc: Exception) -> bool:
    """Only a daily quota counts. Gemini words per-minute limits the same way, so check the quota ID."""
    daily, _ = rate_limit_info(exc)
    return daily


class JudgeClient:
    def __init__(self, *, api_key: str, base_url: str | None, models: list[str], reasoning_effort: str = "low",
                 min_interval: float = 1.0, cache_dir: Path = CACHE_DIR / "judge"):
        self.models = list(models)
        self.index = 0
        self.extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
        self.client = OpenAI(api_key=api_key, base_url=base_url or None, max_retries=0, timeout=120)
        self.min_interval = min_interval
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_call = 0.0
        self.calls = 0
        self.cache_hits = 0
        self.models_used: set[str] = set()

    @property
    def model(self) -> str:
        return self.models[self.index]

    def next_model(self) -> None:
        if self.index + 1 >= len(self.models):
            raise QuotaExhausted(f"daily quota used up for all grader models: {self.models}")
        self.index += 1
        print(f"  grader switched to {self.model}")

    def complete(self, prompt: str, system: str | None = None) -> str:
        key = hashlib.sha256(json.dumps([system, prompt]).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.cache_hits += 1
            cached = json.loads(path.read_text(encoding="utf-8"))
            self.models_used.add(cached["model"])
            return cached["reply"]
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        delay = 5.0
        while True:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                resp = self.client.chat.completions.create(model=self.model, temperature=0, messages=messages, **self.extra)
                reply = (resp.choices[0].message.content or "").strip()
                break
            except RateLimitError as exc:
                daily, retry_after = rate_limit_info(exc)
                if daily:
                    self.next_model()
                    continue
                time.sleep(retry_after + 1 if retry_after else delay)  # per-minute limit: wait and retry
                delay = min(delay * 2, 60)
            except (APITimeoutError, APIConnectionError):
                # A slow or dropped reply: back off and retry, then try the next model.
                time.sleep(delay)
                delay = min(delay * 2, 60)
                if delay >= 60:
                    self.next_model()
                    delay = 5.0
            except APIStatusError as exc:
                if exc.status_code in (500, 502, 503, 504):
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                    if delay >= 60:
                        self.next_model()
                        delay = 5.0
                    continue
                raise
        self.calls += 1
        self.models_used.add(self.model)
        path.write_text(json.dumps({"model": self.model, "reply": reply}), encoding="utf-8")
        return reply

    def complete_json(self, prompt: str, system: str | None = None) -> dict:
        reply = self.complete(prompt, system)
        try:
            return parse_json_object(reply)
        except (ValueError, json.JSONDecodeError):
            retry = self.complete(prompt + "\n\nYour previous reply was not valid JSON. Reply with JSON only.", system)
            return parse_json_object(retry)


class DeepEvalJudge(DeepEvalBaseLLM):
    """Lets DeepEval metrics use the cached JudgeClient."""

    def __init__(self, judge: JudgeClient):
        self.judge = judge
        super().__init__(model=judge.model)

    def load_model(self, *args, **kwargs):
        return self.judge

    def generate(self, prompt: str, schema=None, **kwargs):
        if schema is None:
            return self.judge.complete(prompt)
        data = self.judge.complete_json(prompt + "\n\nReply with a single JSON object only.")
        return schema.model_validate(data)

    async def a_generate(self, prompt: str, schema=None, **kwargs):
        return self.generate(prompt, schema)

    def get_model_name(self, *args, **kwargs) -> str:
        return self.judge.model


def ragas_components(*, api_key: str, base_url: str | None, model: str, reasoning_effort: str):
    """Ragas LLM and embeddings. Ragas caches its own LLM calls on disk."""
    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend
    from ragas.embeddings import BaseRagasEmbedding
    from ragas.llms import llm_factory

    from app.embeddings import get_embedder

    class LocalRagasEmbeddings(BaseRagasEmbedding):
        def __init__(self):
            super().__init__()
            self.embedder = get_embedder()

        def embed_text(self, text: str, **kwargs) -> list[float]:
            return self.embedder.embed_query(text)

        async def aembed_text(self, text: str, **kwargs) -> list[float]:
            return self.embedder.embed_query(text)

    client = AsyncOpenAI(api_key=api_key, base_url=base_url or None, max_retries=8, timeout=120)
    extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
    # Ragas caps grader output at 1024 tokens by default, which truncates the statement list for long
    # answers with code (instructor raises IncompleteOutputException). 8192 leaves ample room.
    llm = llm_factory(model, client=client, cache=DiskCacheBackend(str(CACHE_DIR / "ragas")), temperature=0,
                      max_tokens=8192, **extra)
    return llm, LocalRagasEmbeddings()
