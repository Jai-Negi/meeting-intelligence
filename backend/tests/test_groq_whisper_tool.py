import asyncio
import json

import httpx
import pytest

from app.config import get_settings
from app.tools import groq_whisper_tool
from app.tools.groq_whisper_tool import GroqTranscriptionError, transcribe_audio_groq

GOOD_REPLY = {
    "text": " We agreed to ship on Friday. ",
    "language": "English",
    "segments": [
        {"id": 0, "start": 0.0, "end": 2.5, "text": " We agreed to ship "},
        {"id": 1, "start": 2.5, "end": 4, "text": "on Friday. "},
    ],
}


@pytest.fixture(autouse=True)
def groq_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_whisper_model", "whisper-large-v3-turbo")


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / "standup.m4a"
    path.write_bytes(b"pretend this is audio")
    return path


@pytest.fixture
def groq(monkeypatch):
    """Replaces the network with a fake Groq that records what it was sent."""

    class Fake:
        requests: list[httpx.Request] = []
        status = 200
        body: object = GOOD_REPLY

    def handler(request: httpx.Request) -> httpx.Response:
        Fake.requests.append(request)
        content = Fake.body if isinstance(Fake.body, str) else json.dumps(Fake.body)
        return httpx.Response(Fake.status, content=content)

    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    Fake.requests = []
    Fake.status = 200
    Fake.body = GOOD_REPLY
    monkeypatch.setattr(groq_whisper_tool.httpx, "AsyncClient", client_factory)
    return Fake


def _run(file_path, **kwargs):
    return asyncio.run(transcribe_audio_groq(file_path, **kwargs))


def test_reply_becomes_a_transcript_result(audio_file, groq):
    result = _run(audio_file)

    assert result.text == "We agreed to ship on Friday."
    assert result.language == "English"
    assert [(s.start, s.end, s.text) for s in result.segments] == [
        (0.0, 2.5, "We agreed to ship"),
        (2.5, 4.0, "on Friday."),
    ]


def test_request_has_the_key_model_format_and_audio(audio_file, groq):
    _run(audio_file)

    request = groq.requests[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert request.headers["authorization"] == "Bearer test-key"
    body = request.content
    assert b'name="model"' in body and b"whisper-large-v3-turbo" in body
    assert b'name="response_format"' in body and b"verbose_json" in body
    assert b'filename="standup.m4a"' in body
    assert b"pretend this is audio" in body


def test_model_from_settings_and_explicit_model_are_both_respected(audio_file, groq, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_whisper_model", "whisper-large-v3")
    _run(audio_file)
    assert b"whisper-large-v3" in groq.requests[0].content
    assert b"turbo" not in groq.requests[0].content

    _run(audio_file, model="custom-model")
    assert b"custom-model" in groq.requests[1].content


def test_missing_language_and_segments_fall_back_gracefully(audio_file, groq):
    groq.body = {"text": "hello"}

    result = _run(audio_file)

    assert result.text == "hello"
    assert result.language == "unknown"
    assert result.segments == []


def test_missing_audio_file_raises_without_calling_groq(tmp_path, groq):
    with pytest.raises(FileNotFoundError):
        _run(tmp_path / "nope.m4a")
    assert groq.requests == []


def test_missing_api_key_is_explained_without_calling_groq(audio_file, groq, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")

    with pytest.raises(GroqTranscriptionError, match="GROQ_API_KEY"):
        _run(audio_file)
    assert groq.requests == []


def test_file_over_the_groq_limit_is_refused_without_calling_groq(tmp_path, groq, monkeypatch):
    monkeypatch.setattr(groq_whisper_tool, "GROQ_MAX_UPLOAD_MB", 1)
    big = tmp_path / "long-meeting.m4a"
    big.write_bytes(b"x" * (2 * 1024 * 1024))

    with pytest.raises(GroqTranscriptionError, match=r"2\.0MB.*at most 1MB"):
        _run(big)
    assert groq.requests == []


def test_groq_error_message_is_passed_on(audio_file, groq):
    groq.status = 401
    groq.body = {"error": {"message": "Invalid API Key", "type": "invalid_request_error"}}

    with pytest.raises(GroqTranscriptionError, match="status 401: Invalid API Key"):
        _run(audio_file)


def test_non_json_error_body_is_still_reported(audio_file, groq):
    groq.status = 502
    groq.body = "bad gateway from upstream"

    with pytest.raises(GroqTranscriptionError, match="status 502: bad gateway from upstream"):
        _run(audio_file)
