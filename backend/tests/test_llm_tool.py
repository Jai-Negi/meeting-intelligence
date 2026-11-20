import asyncio

import httpx
import pytest

from app.config import get_settings
from app.errors import PermanentError, is_permanent_http_status
from app.tools import llm_tool
from app.tools.llm_tool import LLMError, LLMPermanentError, generate_completion


@pytest.fixture(autouse=True)
def groq_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")


def _fake_groq(monkeypatch, status, body='{"choices": [{"message": {"content": " hi "}}]}'):
    real_client = httpx.AsyncClient

    def handler(request):
        return httpx.Response(status, content=body)

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(llm_tool.httpx, "AsyncClient", client_factory)


def _complete():
    return asyncio.run(generate_completion("prompt"))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_permanent(status):
    assert is_permanent_http_status(status)


@pytest.mark.parametrize("status", [200, 408, 409, 425, 429, 500, 502, 503])
def test_rate_limits_timeouts_and_server_errors_are_retryable(status):
    assert not is_permanent_http_status(status)


def test_a_successful_reply_is_returned_trimmed(monkeypatch):
    _fake_groq(monkeypatch, 200)

    assert _complete() == "hi"


def test_a_missing_key_is_permanent(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")

    with pytest.raises(LLMPermanentError, match="groq_api_key is not set"):
        _complete()


def test_a_rejected_key_is_permanent(monkeypatch):
    _fake_groq(monkeypatch, 401, '{"error": {"message": "invalid api key"}}')

    with pytest.raises(PermanentError):
        _complete()


@pytest.mark.parametrize("status", [429, 503])
def test_rate_limits_and_outages_stay_retryable(monkeypatch, status):
    _fake_groq(monkeypatch, status, "{}")

    with pytest.raises(LLMError) as exc:
        _complete()
    assert not isinstance(exc.value, PermanentError)
