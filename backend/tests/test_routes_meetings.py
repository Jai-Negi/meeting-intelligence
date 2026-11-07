import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.api import routes_meetings
from app.database.models import Meeting
from app.database.session import SessionLocal

FAKE_AUDIO = b"not really audio, but the route only checks name and size" * 20


def _upload(client, name="standup.mp3", content=FAKE_AUDIO):
    return client.post("/meetings/upload", files={"file": (name, content, "audio/mpeg")})


def _meeting_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Meeting).count()
    finally:
        db.close()


def _seed_meeting(job_id="job-123") -> str:
    db = SessionLocal()
    try:
        db.add(Meeting(id=job_id, filename="standup.mp3", file_path="x", status="processing"))
        db.commit()
    finally:
        db.close()
    return job_id


def _fake_agent(result, calls=None):
    class _Agent:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, **kwargs):
            if calls is not None:
                calls.append(kwargs)
            return result

    return _Agent


def _ok(data):
    return SimpleNamespace(success=True, data=data, error=None)


def _failed(message):
    return SimpleNamespace(success=False, data=None, error=message)


def _transcript():
    return SimpleNamespace(
        text="We agreed to ship on Friday.",
        language="en",
        segments=[SimpleNamespace(start=0.0, end=2.5, text="We agreed to ship on Friday.")],
    )


# upload route


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_valid_upload_is_accepted_and_saved(client, no_background, tmp_path):
    response = _upload(client)

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "standup.mp3"
    assert body["status"] == "processing"

    saved = list((tmp_path / "uploads").iterdir())
    assert len(saved) == 1
    assert saved[0].name == f"{body['job_id']}_standup.mp3"
    assert saved[0].read_bytes() == FAKE_AUDIO


def test_unsupported_file_type_is_rejected_and_nothing_is_stored(client, no_background, tmp_path):
    response = _upload(client, name="notes.txt", content=b"just some text")

    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"]
    assert _meeting_count() == 0
    uploads = tmp_path / "uploads"
    assert not uploads.exists() or list(uploads.iterdir()) == []


def test_empty_file_is_rejected(client, no_background):
    response = _upload(client, content=b"")

    assert response.status_code == 400
    assert "empty" in response.json()["detail"]
    assert _meeting_count() == 0


def test_oversized_file_is_rejected(client, no_background, monkeypatch):
    monkeypatch.setattr(routes_meetings.settings, "max_upload_size_mb", 1)

    response = _upload(client, content=b"x" * (2 * 1024 * 1024))

    assert response.status_code == 400
    assert "exceeds" in response.json()["detail"]
    assert _meeting_count() == 0


# fetching results


def test_unknown_job_returns_404(client):
    response = client.get("/meetings/does-not-exist")
    assert response.status_code == 404


def test_fresh_upload_reports_processing_with_empty_results(client, no_background):
    job_id = _upload(client).json()["job_id"]

    body = client.get(f"/meetings/{job_id}").json()

    assert body["status"] == "processing"
    assert body["text"] is None
    assert body["segments"] == []
    assert body["action_items"] == []
    assert body["timeline"] == []
    assert body["decisions"] == []


# background processing pipeline, with the real agents swapped for fakes


def test_pipeline_saves_transcript_and_all_extractions(client, monkeypatch):
    job_id = _seed_meeting()
    action = SimpleNamespace(description="Send the deck", owner="Sam", due_date="Friday")
    event = SimpleNamespace(topic="Launch", summary="Discussed the launch plan", approx_time="00:01")
    decision = SimpleNamespace(decision="Ship on Friday", context="Team agreed")

    monkeypatch.setattr(routes_meetings, "TranscriptionAgent", _fake_agent(_ok(_transcript())))
    monkeypatch.setattr(routes_meetings, "ActionItemAgent", _fake_agent(_ok([action])))
    monkeypatch.setattr(routes_meetings, "TimelineAgent", _fake_agent(_ok([event])))
    monkeypatch.setattr(routes_meetings, "DecisionAgent", _fake_agent(_ok([decision])))

    asyncio.run(routes_meetings._process_transcription(job_id, Path("standup.mp3")))

    body = client.get(f"/meetings/{job_id}").json()
    assert body["status"] == "completed"
    assert body["text"] == "We agreed to ship on Friday."
    assert body["language"] == "en"
    assert len(body["segments"]) == 1
    assert body["action_items"] == [
        {"description": "Send the deck", "owner": "Sam", "due_date": "Friday"}
    ]
    assert body["timeline"][0]["topic"] == "Launch"
    assert body["decisions"][0]["decision"] == "Ship on Friday"


def test_failed_transcription_marks_job_failed_and_skips_extraction(client, monkeypatch):
    job_id = _seed_meeting()
    extraction_calls = []

    monkeypatch.setattr(routes_meetings, "TranscriptionAgent", _fake_agent(_failed("whisper exploded")))
    monkeypatch.setattr(routes_meetings, "ActionItemAgent", _fake_agent(_ok([]), extraction_calls))
    monkeypatch.setattr(routes_meetings, "TimelineAgent", _fake_agent(_ok([]), extraction_calls))
    monkeypatch.setattr(routes_meetings, "DecisionAgent", _fake_agent(_ok([]), extraction_calls))

    asyncio.run(routes_meetings._process_transcription(job_id, Path("standup.mp3")))

    body = client.get(f"/meetings/{job_id}").json()
    assert body["status"] == "failed"
    assert body["error"] == "whisper exploded"
    assert body["text"] is None
    assert extraction_calls == []


def test_one_failing_extraction_does_not_block_the_others(client, monkeypatch):
    job_id = _seed_meeting()
    event = SimpleNamespace(topic="Launch", summary="Discussed the launch plan", approx_time=None)
    decision = SimpleNamespace(decision="Ship on Friday", context=None)

    monkeypatch.setattr(routes_meetings, "TranscriptionAgent", _fake_agent(_ok(_transcript())))
    monkeypatch.setattr(routes_meetings, "ActionItemAgent", _fake_agent(_failed("llm timeout")))
    monkeypatch.setattr(routes_meetings, "TimelineAgent", _fake_agent(_ok([event])))
    monkeypatch.setattr(routes_meetings, "DecisionAgent", _fake_agent(_ok([decision])))

    asyncio.run(routes_meetings._process_transcription(job_id, Path("standup.mp3")))

    body = client.get(f"/meetings/{job_id}").json()
    assert body["status"] == "completed"
    assert body["text"] == "We agreed to ship on Friday."
    assert body["action_items"] == []
    assert len(body["timeline"]) == 1
    assert len(body["decisions"]) == 1


def test_meeting_is_only_completed_once_extractions_are_saved(client, monkeypatch):
    job_id = _seed_meeting()
    status_seen_during_extraction = []

    class _SpyAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, **kwargs):
            db = SessionLocal()
            try:
                status_seen_during_extraction.append(db.get(Meeting, job_id).status)
            finally:
                db.close()
            return _ok([])

    monkeypatch.setattr(routes_meetings, "TranscriptionAgent", _fake_agent(_ok(_transcript())))
    monkeypatch.setattr(routes_meetings, "ActionItemAgent", _SpyAgent)
    monkeypatch.setattr(routes_meetings, "TimelineAgent", _fake_agent(_ok([])))
    monkeypatch.setattr(routes_meetings, "DecisionAgent", _fake_agent(_ok([])))

    asyncio.run(routes_meetings._process_transcription(job_id, Path("standup.mp3")))

    assert status_seen_during_extraction == ["processing"]
    assert client.get(f"/meetings/{job_id}").json()["status"] == "completed"
