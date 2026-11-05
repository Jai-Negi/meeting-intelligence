from fastapi.testclient import TestClient

from app.database.maintenance import INTERRUPTED_MESSAGE, fail_interrupted_jobs
from app.database.models import Meeting
from app.database.session import SessionLocal
from app.main import app


def _seed(job_id: str, status: str, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(
            Meeting(id=job_id, filename=f"{job_id}.mp3", file_path="x", status=status, error=error)
        )
        db.commit()
    finally:
        db.close()


def _get(job_id: str) -> Meeting:
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter_by(id=job_id).first()
        db.expunge(meeting)
        return meeting
    finally:
        db.close()


def test_processing_jobs_are_marked_failed_with_a_reason(client):
    _seed("stuck", "processing")

    changed = fail_interrupted_jobs()

    assert changed == 1
    meeting = _get("stuck")
    assert meeting.status == "failed"
    assert meeting.error == INTERRUPTED_MESSAGE


def test_finished_jobs_are_left_alone(client):
    _seed("done", "completed")
    _seed("broken", "failed", error="whisper exploded")

    changed = fail_interrupted_jobs()

    assert changed == 0
    assert _get("done").status == "completed"
    assert _get("done").error is None
    assert _get("broken").error == "whisper exploded"


def test_only_processing_jobs_are_counted(client):
    _seed("a", "processing")
    _seed("b", "processing")
    _seed("c", "completed")

    assert fail_interrupted_jobs() == 2


def test_sweep_runs_automatically_on_server_startup(client):
    _seed("stuck", "processing")

    with TestClient(app):
        pass

    assert _get("stuck").status == "failed"


def test_swept_job_can_then_be_deleted(client):
    _seed("stuck", "processing")
    assert client.delete("/meetings/stuck").status_code == 409

    fail_interrupted_jobs()

    assert client.delete("/meetings/stuck").status_code == 204
