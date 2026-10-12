"""Chat model client for any OpenAI-compatible endpoint (OpenAI, Gemini, Groq, OpenRouter)."""

import json
import logging
import re
import time
from functools import lru_cache
from typing import Protocol

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


class ChatModel(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class LLMUnavailable(RuntimeError):
    """The model provider failed after retries and fallbacks (quota, outage, bad key)."""


RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")


def rate_limit_info(exc: Exception) -> tuple[bool, float | None]:
    """(is_daily_quota, suggested retry delay in seconds) from a 429 error body, when the provider gives them."""
    text = str(getattr(exc, "body", None) or exc)
    daily = "PerDay" in text
    match = RETRY_DELAY_RE.search(text)
    return daily, float(match.group(1)) if match else None


class OpenAICompatibleChat:
    """Calls the primary model, then each fallback model in order.

    A per-minute rate limit waits for the provider's suggested delay (up to
    MAX_RATE_LIMIT_WAIT seconds) and retries the same model. A daily quota, a
    missing model, or repeated overload moves on to the next model.
    """

    ATTEMPTS_PER_MODEL = 3
    MAX_RATE_LIMIT_WAIT = 30.0

    def __init__(self, settings: Settings):
        from openai import OpenAI

        if not settings.llm_api_key:
            raise LLMUnavailable("LLM_API_KEY is not set")
        self.name = settings.llm_model
        self.models = [settings.llm_model] + [m for m in settings.fallback_models if m != settings.llm_model]
        self._temperature = settings.llm_temperature
        self._extra = {"reasoning_effort": settings.llm_reasoning_effort} if settings.llm_reasoning_effort else {}
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    def complete(self, system: str, user: str) -> str:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

        last_error = "no models configured"
        for model in self.models:
            for attempt in range(self.ATTEMPTS_PER_MODEL):
                try:
                    resp = self._client.chat.completions.create(
                        model=model,
                        temperature=self._temperature,
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                        **self._extra,
                    )
                    return (resp.choices[0].message.content or "").strip()
                except RateLimitError as exc:
                    daily, retry_after = rate_limit_info(exc)
                    last_error = f"{model}: rate limited ({'daily quota' if daily else 'per-minute limit'})"
                    wait = retry_after if retry_after is not None else 5.0 * (attempt + 1)
                    if daily or wait > self.MAX_RATE_LIMIT_WAIT:
                        break
                    if attempt + 1 < self.ATTEMPTS_PER_MODEL:
                        time.sleep(wait)
                    continue
                except (APIConnectionError, APITimeoutError) as exc:
                    last_error = f"{model}: {exc}"
                except APIStatusError as exc:
                    last_error = f"{model}: {exc.status_code} {exc.message}"
                    if exc.status_code < 500 and exc.status_code != 404:
                        raise LLMUnavailable(last_error) from exc  # bad key or bad request: fallbacks will not help
                    if exc.status_code == 404:
                        break  # model not available on this account: go to the next one
                if attempt + 1 < self.ATTEMPTS_PER_MODEL:
                    time.sleep(1.5 * (attempt + 1))
            log.warning("model %s unavailable, trying next fallback (%s)", model, last_error[:200])
        raise LLMUnavailable(last_error)


def parse_json_object(text: str) -> dict:
    """Parse the first JSON object in a model reply, tolerating code fences and surrounding prose."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    return json.loads(match.group(0))


@lru_cache
def get_chat_model() -> ChatModel:
    return OpenAICompatibleChat(get_settings())
