"""The eval grader client retries slow or dropped replies instead of crashing the run."""

import httpx
import openai

from eval.judge import JudgeClient


def test_timeout_is_retried_then_answered(tmp_path, monkeypatch):
    judge = JudgeClient(api_key="k", base_url="http://x", models=["a", "b"], reasoning_effort="", min_interval=0,
                        cache_dir=tmp_path)
    outcomes = [openai.APITimeoutError(request=httpx.Request("POST", "http://x")), "ok"]

    class Reply:
        def __init__(self, text):
            self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]

    def create(model, **kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Reply(outcome)

    monkeypatch.setattr(judge.client.chat.completions, "create", create)
    monkeypatch.setattr("eval.judge.time.sleep", lambda s: None)
    assert judge.complete("prompt") == "ok"
    assert judge.model == "a"
