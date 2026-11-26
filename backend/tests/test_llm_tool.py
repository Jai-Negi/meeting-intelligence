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
    monkeypatch.setattr(settings, "llm_fallback_providers", "")


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


# fallback between providers


def _fake_providers(monkeypatch, **outcomes):
    """Replaces each provider call with a reply or an error, and records the order they were tried."""
    tried = []

    def make(name):
        async def call(prompt, system, **kwargs):
            tried.append(name)
            outcome = outcomes[name]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return call

    monkeypatch.setattr(llm_tool, "_call_groq", make("groq"))
    monkeypatch.setattr(llm_tool, "_call_anthropic", make("anthropic"))
    monkeypatch.setattr(llm_tool, "_call_ollama", make("ollama"))
    return tried


def _use_chain(monkeypatch, main, fallbacks):
    monkeypatch.setattr(get_settings(), "llm_provider", main)
    monkeypatch.setattr(get_settings(), "llm_fallback_providers", fallbacks)


def test_the_chain_starts_with_the_main_provider_and_skips_repeats_and_blanks(monkeypatch):
    _use_chain(monkeypatch, "groq", " Anthropic , ,groq,ollama")

    assert get_settings().llm_provider_chain == ["groq", "anthropic", "ollama"]


def test_without_fallbacks_only_the_main_provider_is_used(monkeypatch):
    tried = _fake_providers(monkeypatch, groq=LLMError("groq is down"), anthropic="unused", ollama="unused")

    with pytest.raises(LLMError, match="^groq is down$"):
        _complete()
    assert tried == ["groq"]


def test_a_working_main_provider_never_touches_the_fallbacks(monkeypatch):
    _use_chain(monkeypatch, "groq", "anthropic")
    tried = _fake_providers(monkeypatch, groq="from groq", anthropic="from anthropic", ollama="unused")

    assert _complete() == "from groq"
    assert tried == ["groq"]


def test_a_failing_main_provider_falls_back_in_order(monkeypatch):
    _use_chain(monkeypatch, "groq", "anthropic,ollama")
    tried = _fake_providers(
        monkeypatch,
        groq=LLMError("rate limited"),
        anthropic=LLMPermanentError("anthropic_api_key is not set"),
        ollama="from ollama",
    )

    assert _complete() == "from ollama"
    assert tried == ["groq", "anthropic", "ollama"]


def test_when_every_provider_fails_permanently_the_error_is_permanent(monkeypatch):
    _use_chain(monkeypatch, "groq", "anthropic")
    _fake_providers(
        monkeypatch,
        groq=LLMPermanentError("groq rejected the request"),
        anthropic=LLMPermanentError("anthropic_api_key is not set"),
        ollama="unused",
    )

    with pytest.raises(LLMPermanentError) as exc:
        _complete()
    assert "groq rejected the request" in str(exc.value)
    assert "anthropic_api_key is not set" in str(exc.value)


def test_when_any_provider_failure_is_temporary_the_error_stays_retryable(monkeypatch):
    _use_chain(monkeypatch, "groq", "anthropic")
    _fake_providers(
        monkeypatch,
        groq=LLMError("rate limited"),
        anthropic=LLMPermanentError("anthropic_api_key is not set"),
        ollama="unused",
    )

    with pytest.raises(LLMError) as exc:
        _complete()
    assert not isinstance(exc.value, PermanentError)
    assert "every llm provider failed" in str(exc.value)


def test_an_unknown_provider_is_permanent(monkeypatch):
    _use_chain(monkeypatch, "openai", "")

    with pytest.raises(LLMPermanentError, match="unknown llm provider: openai"):
        _complete()


def test_an_unknown_fallback_does_not_hide_a_working_one(monkeypatch):
    _use_chain(monkeypatch, "openai", "groq")
    _fake_providers(monkeypatch, groq="from groq", anthropic="unused", ollama="unused")

    assert _complete() == "from groq"
