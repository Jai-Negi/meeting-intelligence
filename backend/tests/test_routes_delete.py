from app.database.models import (
    ActionItem,
    Decision,
    Meeting,
    TimelineEvent,
    Transcript,
    TranscriptSegment,
)
from app.database.session import SessionLocal


def _seed_full_meeting(file_path: str, status: str = "completed", job_id: str = "job-1") -> str:
    db = SessionLocal()
    try:
        db.add(Meeting(id=job_id, filename="standup.mp3", file_path=file_path, status=status))
        db.flush()
        transcript = Transcript(meeting_id=job_id, text="hello", language="en")
        db.add(transcript)
        db.flush()
        db.add(TranscriptSegment(transcript_id=transcript.id, start=0.0, end=1.0, text="hello"))
        db.add(ActionItem(meeting_id=job_id, description="do a thing"))
        db.add(TimelineEvent(meeting_id=job_id, topic="t", summary="s"))
        db.add(Decision(meeting_id=job_id, decision="d"))
        db.commit()
    finally:
        db.close()
    return job_id


def _row_counts() -> dict:
    db = SessionLocal()
    try:
        return {
            "meetings": db.query(Meeting).count(),
            "transcripts": db.query(Transcript).count(),
            "segments": db.query(TranscriptSegment).count(),
            "action_items": db.query(ActionItem).count(),
            "timeline_events": db.query(TimelineEvent).count(),
            "decisions": db.query(Decision).count(),
        }
    finally:
        db.close()


def test_delete_removes_meeting_and_everything_attached(client, tmp_path):
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"audio")
    job_id = _seed_full_meeting(str(audio))

    response = client.delete(f"/meetings/{job_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert _row_counts() == {
        "meetings": 0,
        "transcripts": 0,
        "segments": 0,
        "action_items": 0,
        "timeline_events": 0,
        "decisions": 0,
    }
    assert not audio.exists()
    assert client.get(f"/meetings/{job_id}").status_code == 404


def test_delete_unknown_job_returns_404(client):
    assert client.delete("/meetings/does-not-exist").status_code == 404


def test_delete_still_works_when_audio_file_is_already_gone(client, tmp_path):
    job_id = _seed_full_meeting(str(tmp_path / "missing.mp3"))

    assert client.delete(f"/meetings/{job_id}").status_code == 204
    assert _row_counts()["meetings"] == 0


def test_delete_is_refused_while_processing(client, tmp_path):
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"audio")
    job_id = _seed_full_meeting(str(audio), status="processing")

    response = client.delete(f"/meetings/{job_id}")

    assert response.status_code == 409
    assert "still processing" in response.json()["detail"]
    assert _row_counts()["meetings"] == 1
    assert audio.exists()


def test_delete_failed_meeting_is_allowed(client, tmp_path):
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"audio")
    job_id = _seed_full_meeting(str(audio), status="failed")

    assert client.delete(f"/meetings/{job_id}").status_code == 204
    assert not audio.exists()


def test_deleted_meeting_disappears_from_list(client, tmp_path):
    job_id = _seed_full_meeting(str(tmp_path / "a.mp3"))
    assert len(client.get("/meetings").json()) == 1

    client.delete(f"/meetings/{job_id}")

    assert client.get("/meetings").json() == []
