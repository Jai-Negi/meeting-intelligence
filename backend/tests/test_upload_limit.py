import pytest
from pydantic import ValidationError

from app import config
from app.api import routes_meetings
from app.config import Settings

TWO_MB = b"x" * (2 * 1024 * 1024)


def _upload(client, content=TWO_MB):
    return client.post("/meetings/upload", files={"file": ("long.mp3", content, "audio/mpeg")})


def test_local_transcription_uses_the_configured_limit():
    assert Settings(transcription_provider="local", max_upload_size_mb=500).effective_max_upload_mb == 500


def test_groq_transcription_caps_the_limit_at_what_groq_accepts():
    assert Settings(transcription_provider="groq", max_upload_size_mb=500).effective_max_upload_mb == 25


def test_a_lower_configured_limit_still_wins_with_groq():
    assert Settings(transcription_provider="groq", max_upload_size_mb=10).effective_max_upload_mb == 10


def test_an_unknown_provider_is_rejected_at_startup():
    with pytest.raises(ValidationError):
        Settings(transcription_provider="banana")


def test_upload_over_the_groq_limit_is_refused_up_front(client, no_background, monkeypatch):
    monkeypatch.setattr(routes_meetings.settings, "transcription_provider", "groq")
    monkeypatch.setattr(config, "GROQ_MAX_UPLOAD_MB", 1)

    response = _upload(client)

    assert response.status_code == 400
    assert "exceeds the 1MB limit" in response.json()["detail"]


def test_the_same_upload_is_fine_with_local_transcription(client, no_background, monkeypatch):
    monkeypatch.setattr(routes_meetings.settings, "transcription_provider", "local")
    monkeypatch.setattr(config, "GROQ_MAX_UPLOAD_MB", 1)

    assert _upload(client).status_code == 200
