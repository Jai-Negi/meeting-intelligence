import logging

import httpx

from app.config import get_settings
from app.errors import PermanentError, is_permanent_http_status

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMPermanentError(LLMError, PermanentError):
    """An LLM failure that retrying cannot fix, such as a missing key or a rejected request."""


def _http_error(provider: str, exc: httpx.HTTPError) -> LLMError:
    if isinstance(exc, httpx.HTTPStatusError) and is_permanent_http_status(exc.response.status_code):
        return LLMPermanentError(f"{provider} rejected the request: {exc}")
    return LLMError(f"{provider} call failed: {exc}")


async def generate_completion(prompt: str, system: str | None = None) -> str:
    """
    Sends a prompt to the configured LLM provider and returns the raw text
    response. This is the one place in the codebase that knows how to talk
    to Groq, Ollama, or Anthropic, every agent that needs an LLM call goes
    through here instead of calling a provider SDK directly.

    If LLM_FALLBACK_PROVIDERS is set and the main provider fails, each
    fallback is tried in order before giving up. When every provider fails,
    the error is only permanent if every failure was permanent, so a
    provider that was merely rate limited still lets the agent retry.
    """
    settings = get_settings()
    chain = settings.llm_provider_chain
    errors: list[LLMError] = []

    for index, provider in enumerate(chain):
        try:
            return await _call_provider(provider, prompt=prompt, system=system)
        except LLMError as exc:
            errors.append(exc)
            if index + 1 < len(chain):
                logger.warning(
                    "llm provider failed, trying the next one",
                    extra={"provider": provider, "next_provider": chain[index + 1], "error": str(exc)},
                )

    if len(errors) == 1:
        raise errors[0]

    message = "every llm provider failed: " + "; ".join(str(exc) for exc in errors)
    if all(isinstance(exc, PermanentError) for exc in errors):
        raise LLMPermanentError(message)
    raise LLMError(message)


async def _call_provider(provider: str, prompt: str, system: str | None) -> str:
    settings = get_settings()

    if provider == "groq":
        return await _call_groq(prompt=prompt, system=system, api_key=settings.groq_api_key)

    if provider == "anthropic":
        return await _call_anthropic(prompt=prompt, system=system, api_key=settings.anthropic_api_key)

    if provider == "ollama":
        return await _call_ollama(prompt=prompt, system=system, base_url=settings.ollama_base_url)

    raise LLMPermanentError(f"unknown llm provider: {provider}")


async def _call_groq(prompt: str, system: str | None, api_key: str) -> str:
    if not api_key:
        raise LLMPermanentError("groq_api_key is not set")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "openai/gpt-oss-20b", "messages": messages},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.error("groq call failed", extra={"error": str(exc)})
        raise _http_error("groq", exc) from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMError(f"unexpected groq response shape: {exc}") from exc


async def _call_anthropic(prompt: str, system: str | None, api_key: str) -> str:
    if not api_key:
        raise LLMPermanentError("anthropic_api_key is not set")

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.error("anthropic call failed", extra={"error": str(exc)})
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int) and is_permanent_http_status(status_code):
            raise LLMPermanentError(f"anthropic rejected the request: {exc}") from exc
        raise LLMError(f"anthropic call failed: {exc}") from exc

    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "".join(text_blocks).strip()


async def _call_ollama(prompt: str, system: str | None, base_url: str) -> str:
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url}/api/generate",
                json={"model": "llama3", "prompt": full_prompt, "stream": False},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.error("ollama call failed", extra={"error": str(exc)})
        raise _http_error("ollama", exc) from exc

    return data.get("response", "").strip()
