"""LLMClient 测试（mock OpenAI SDK）。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from csm_qa.llm import LLMClient


def _fake_response(content="hello", pt=10, ct=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct),
    )


def _make_client():
    with patch("csm_qa.llm.OpenAI") as mock_openai:
        instance = MagicMock()
        mock_openai.return_value = instance
        client = LLMClient(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )
        return client, instance


def test_init_requires_api_key():
    with pytest.raises(ValueError):
        LLMClient(api_key="", base_url="x", model="y")


def test_chat_returns_text_and_usage():
    client, openai_instance = _make_client()
    openai_instance.chat.completions.create.return_value = _fake_response()

    text, usage = client.chat([{"role": "user", "content": "hi"}])

    assert text == "hello"
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5
    assert usage.total_tokens == 15


def test_chat_passes_overrides():
    client, openai_instance = _make_client()
    openai_instance.chat.completions.create.return_value = _fake_response()

    client.chat(
        [{"role": "user", "content": "hi"}],
        max_tokens=100,
        temperature=0.0,
    )
    kwargs = openai_instance.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["max_tokens"] == 100
    assert kwargs["temperature"] == 0.0


def test_chat_retries_on_rate_limit_then_succeeds(monkeypatch):
    from openai import RateLimitError

    monkeypatch.setattr("csm_qa.llm.time.sleep", lambda *_: None)
    client, openai_instance = _make_client()

    err = RateLimitError(
        "rate", response=MagicMock(status_code=429), body=None
    )
    openai_instance.chat.completions.create.side_effect = [err, _fake_response()]

    text, _ = client.chat([{"role": "user", "content": "hi"}])
    assert text == "hello"
    assert openai_instance.chat.completions.create.call_count == 2


def test_chat_raises_after_max_retries(monkeypatch):
    from openai import RateLimitError

    monkeypatch.setattr("csm_qa.llm.time.sleep", lambda *_: None)
    client, openai_instance = _make_client()
    err = RateLimitError(
        "rate", response=MagicMock(status_code=429), body=None
    )
    openai_instance.chat.completions.create.side_effect = err

    with pytest.raises(RateLimitError):
        client.chat([{"role": "user", "content": "hi"}])
    assert openai_instance.chat.completions.create.call_count == client.max_retries
