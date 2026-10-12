"""Retry and fallback behaviour of the chat client, without network calls."""

import httpx
import openai
import pytest

from app.config import Settings
from app.llm import LLMUnavailable, OpenAICompatibleChat, parse_json_object, rate_limit_info


def rate_limit(quota_id: str, retry_delay: str | None = None) -> openai.RateLimitError:
    details = [{"violations": [{"quotaId": quota_id}]}]
    if retry_delay:
        details.append({"retryDelay": retry_delay})
    body = [{"error": {"code": 429, "details": details}}]
    resp = httpx.Response(429, request=httpx.Request("POST", "http://x"))
    return openai.RateLimitError("quota", response=resp, body=body)


def status_error(code: int) -> openai.APIStatusError:
    resp = httpx.Response(code, request=httpx.Request("POST", "http://x"))
    return openai.APIStatusError(f"status {code}", response=resp, body=None)


class Reply:
    def __init__(self, text):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]


def make_chat(monkeypatch, outcomes: dict[str, list]):
    settings = Settings(llm_api_key="k", llm_model="primary", llm_fallback_models="backup", llm_reasoning_effort="")
    chat = OpenAICompatibleChat(settings)
    calls = []

    def create(model, **kwargs):
        calls.append(model)
        outcome = outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Reply(outcome)

    monkeypatch.setattr(chat._client.chat.completions, "create", create)
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)
    return chat, calls


def test_daily_quota_moves_to_fallback(monkeypatch):
    chat, calls = make_chat(monkeypatch, {"primary": [rate_limit("GenerateRequestsPerDayPerProjectPerModel")], "backup": ["ok"]})
    assert chat.complete("s", "u") == "ok"
    assert calls == ["primary", "backup"]


def test_per_minute_limit_retries_same_model(monkeypatch):
    chat, calls = make_chat(monkeypatch, {"primary": [rate_limit("PerMinute", "3s"), "ok"], "backup": []})
    assert chat.complete("s", "u") == "ok"
    assert calls == ["primary", "primary"]


def test_long_retry_delay_moves_to_fallback(monkeypatch):
    chat, calls = make_chat(monkeypatch, {"primary": [rate_limit("PerMinute", "55s")], "backup": ["ok"]})
    assert chat.complete("s", "u") == "ok"
    assert calls == ["primary", "backup"]


def test_overload_then_fallback(monkeypatch):
    chat, calls = make_chat(monkeypatch, {"primary": [status_error(503)] * 3, "backup": ["ok"]})
    assert chat.complete("s", "u") == "ok"
    assert calls == ["primary"] * 3 + ["backup"]


def test_bad_request_is_not_retried(monkeypatch):
    chat, calls = make_chat(monkeypatch, {"primary": [status_error(401)], "backup": ["ok"]})
    with pytest.raises(LLMUnavailable):
        chat.complete("s", "u")
    assert calls == ["primary"]


def test_all_models_exhausted_raises(monkeypatch):
    daily = rate_limit("PerDay")
    chat, _ = make_chat(monkeypatch, {"primary": [daily], "backup": [daily]})
    with pytest.raises(LLMUnavailable):
        chat.complete("s", "u")


def test_rate_limit_info_parses_gemini_body():
    assert rate_limit_info(rate_limit("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "23s")) == (False, 23.0)
    assert rate_limit_info(rate_limit("GenerateRequestsPerDayPerProjectPerModel-FreeTier")) == (True, None)


def test_parse_json_object_tolerates_fences():
    assert parse_json_object('```json\n{"sufficient": true}\n```') == {"sufficient": True}
