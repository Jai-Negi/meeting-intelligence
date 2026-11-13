import asyncio

import pytest

from app.agents import transcription_agent
from app.agents.transcription_agent import TranscriptionAgent
from app.config import get_settings
from app.tools.whisper_tool import TranscriptResult, TranscriptSegment


def _result(label: str) -> TranscriptResult:
    return TranscriptResult(
        text=label, language="en", segments=[TranscriptSegment(start=0.0, end=1.0, text=label)]
    )


@pytest.fixture
def fake_transcribers(monkeypatch):
    """Replaces both transcribers and records which one was used and how."""
    calls = []

    async def local(file_path, model_size="base"):
        calls.append(("local", str(file_path), model_size))
        return _result("from local")

    async def groq(file_path):
        calls.append(("groq", str(file_path)))
        return _result("from groq")

    monkeypatch.setattr(transcription_agent, "transcribe_audio", local)
    monkeypatch.setattr(transcription_agent, "transcribe_audio_groq", groq)
    return calls


def _execute(agent, file_path="meeting.m4a"):
    agent.retry_backoff_seconds = 0
    return asyncio.run(agent.execute(file_path=file_path))


def test_local_provider_uses_local_whisper_with_the_model_size(fake_transcribers):
    result = _execute(TranscriptionAgent(model_size="small", provider="local"))

    assert result.success
    assert result.data.text == "from local"
    assert fake_transcribers == [("local", "meeting.m4a", "small")]


def test_groq_provider_uses_groq(fake_transcribers):
    result = _execute(TranscriptionAgent(provider="groq"))

    assert result.success
    assert result.data.text == "from groq"
    assert fake_transcribers == [("groq", "meeting.m4a")]


@pytest.mark.parametrize("configured", ["local", "groq"])
def test_provider_defaults_to_the_setting(fake_transcribers, monkeypatch, configured):
    monkeypatch.setattr(get_settings(), "transcription_provider", configured)

    assert TranscriptionAgent().provider == configured


def test_an_explicit_provider_overrides_the_setting(fake_transcribers, monkeypatch):
    monkeypatch.setattr(get_settings(), "transcription_provider", "groq")

    assert TranscriptionAgent(provider="local").provider == "local"


def test_a_transcriber_failure_is_reported_with_its_message(monkeypatch):
    async def broken(file_path):
        raise RuntimeError("audio file is 30.0MB, Groq accepts at most 25MB per file")

    monkeypatch.setattr(transcription_agent, "transcribe_audio_groq", broken)

    result = _execute(TranscriptionAgent(provider="groq"))

    assert not result.success
    assert "Groq accepts at most 25MB" in result.error
