from types import SimpleNamespace

from app.api import routes_meetings
from app.database.models import ActionItem, Meeting, Transcript, TranscriptSegment
from app.database.session import SessionLocal


def _seed_failed(file_path: str, status: str = "failed", job_id: str = "job-1") -> str:
    db = SessionLocal()
    try:
        db.add(
            Meeting(
                id=job_id,
                filename="standup.mp3",
                file_path=file_path,
                status=status,
                error="whisper exploded" if status == "failed" else None,
            )
        )
        db.commit()
    finally:
        db.close()
    return job_id


def _fake_agent(result):
    class _Agent:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, **kwargs):
            return result

    return _Agent


def _ok(data):
    return SimpleNamespace(success=True, data=data, error=None)


def _failed(message):
    return SimpleNamespace(success=False, data=None, error=message)


def _transcript(text="We agreed to ship on Friday."):
    return SimpleNamespace(
        text=text,
        language="en",
        segments=[SimpleNamespace(start=0.0, end=2.5, text=text)],
    )


def _use_fake_agents(monkeypatch, transcription, actions=None):
    monkeypatch.setattr(routes_meetings, "TranscriptionAgent", _fake_agent(transcription))
    monkeypatch.setattr(routes_meetings, "ActionItemAgent", _fake_agent(_ok(actions or [])))
    monkeypatch.setattr(routes_meetings, "TimelineAgent", _fake_agent(_ok([])))
    monkeypatch.setattr(routes_meetings, "DecisionAgent", _fake_agent(_ok([])))


def test_retry_reruns_the_pipeline_for_a_failed_meeting(client, monkeypatch, tmp_path):
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"audio")
    job_id = _seed_failed(str(audio))
    _use_fake_agents(monkeypatch, _ok(_transcript()))

    response = client.post(f"/meetings/{job_id}/retry")

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    body = client.get(f"/meetings/{job_id}").json()
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["text"] == "We agreed to ship on Friday."


def test_retry_that_fails_again_goes_back_to_failed_with_the_new_error(client, monkeypatch, tmp_path):
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"audio")
    job_id = _seed_failed(str(audio))
    _use_fake_agents(monkeypatch, _failed("still broken"))

    client.post(f"/meetings/{job_id}/retry")

    body = client.get(f"/meetings/{job_id}").json()
    assert body["status"] == "failed"
    assert body["error"] == "still broken"


def test_retry_clears_leftovers_so_results_are_not_duplicated(client, monkeypatch, tmp_path):
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"audio")
    job_id = _seed_failed(str(audio))
    db = SessionLocal()
    try:
        old = Transcript(meeting_id=job_id, text="old text", language="en")
        db.add(old)
        db.flush()
        db.add(TranscriptSegment(transcript_id=old.id, start=0.0, end=1.0, text="old text"))
        db.add(ActionItem(meeting_id=job_id, description="stale item"))
        db.commit()
    finally:
        db.close()
    new_item = SimpleNamespace(description="fresh item", owner=None, due_date=None)
    _use_fake_agents(monkeypatch, _ok(_transcript("new text")), actions=[new_item])

    client.post(f"/meetings/{job_id}/retry")

    body = client.get(f"/meetings/{job_id}").json()
    assert body["text"] == "new text"
    assert [s["text"] for s in body["segments"]] == ["new text"]
    assert [a["description"] for a in body["action_items"]] == ["fresh item"]


def test_retry_unknown_job_returns_404(client):
    assert client.post("/meetings/does-not-exist/retry").status_code == 404


def test_retry_is_refused_unless_the_meeting_failed(client, tmp_path):
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"audio")
    _seed_failed(str(audio), status="completed", job_id="done")
    _seed_failed(str(audio), status="processing", job_id="busy")

    for job_id in ("done", "busy"):
        response = client.post(f"/meetings/{job_id}/retry")
        assert response.status_code == 409
        assert "only failed meetings" in response.json()["detail"]


def test_retry_is_refused_when_the_audio_file_is_gone(client, tmp_path):
    job_id = _seed_failed(str(tmp_path / "missing.mp3"))

    response = client.post(f"/meetings/{job_id}/retry")

    assert response.status_code == 409
    assert "no longer on the server" in response.json()["detail"]
    assert client.get(f"/meetings/{job_id}").json()["status"] == "failed"
