"""Regression: an OpenRouter HTTP 200 with no `choices` is a transient error.

The free Nemotron endpoint intermittently answers 200 with an error-shaped body
(`{"error": {...}}`, no `choices`). That must be retried with backoff like a 429,
not surfaced as a bare `KeyError: 'choices'` — narrative synthesis has no rules
fallback, so an unretried failure zeroes the narrative.
"""
import time

import pytest

from src.agents import llm_client
from src.agents.llm_client import TransientLLMError, _call_with_retry, _openrouter_chat


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


_ERROR_BODY = {"error": {"message": "rate limited: free-models-per-minute", "code": 429}}
_OK_BODY = {
    "choices": [{"message": {"content": "ok"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
}


@pytest.fixture(autouse=True)
def _fast_and_keyed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)


def test_retries_past_choicesless_200_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(*_args, **_kwargs):
        calls["n"] += 1
        return _FakeResp(_ERROR_BODY if calls["n"] < 3 else _OK_BODY)

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    text, usage = _call_with_retry(_openrouter_chat, "p", 10, 0.0)

    assert text == "ok"
    assert usage["prompt_tokens"] == 3
    assert calls["n"] == 3


def test_raises_transient_after_exhausting_retries(monkeypatch):
    calls = {"n": 0}

    def fake_post(*_args, **_kwargs):
        calls["n"] += 1
        return _FakeResp(_ERROR_BODY)

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    with pytest.raises(TransientLLMError):
        _call_with_retry(_openrouter_chat, "p", 10, 0.0, max_retries=4)

    assert calls["n"] == 5  # initial attempt + 4 retries
