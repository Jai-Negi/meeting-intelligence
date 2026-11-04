from datetime import datetime, timedelta

from app.database.models import Meeting
from app.database.session import SessionLocal


def _seed(count: int) -> None:
    """Creates meetings named meeting-0, meeting-1, ... where a higher number is newer."""
    base = datetime(2026, 1, 1, 9, 0, 0)
    db = SessionLocal()
    try:
        for i in range(count):
            db.add(
                Meeting(
                    id=f"job-{i}",
                    filename=f"meeting-{i}.mp3",
                    file_path="x",
                    status="completed",
                    created_at=base + timedelta(hours=i),
                )
            )
        db.commit()
    finally:
        db.close()


def test_list_is_empty_when_nothing_uploaded(client):
    response = client.get("/meetings")

    assert response.status_code == 200
    assert response.json() == []


def test_list_returns_newest_first(client):
    _seed(3)

    body = client.get("/meetings").json()

    assert [m["filename"] for m in body] == ["meeting-2.mp3", "meeting-1.mp3", "meeting-0.mp3"]


def test_list_items_have_summary_fields_only(client):
    _seed(1)

    item = client.get("/meetings").json()[0]

    assert set(item.keys()) == {"job_id", "filename", "status", "created_at"}
    assert item["job_id"] == "job-0"
    assert item["status"] == "completed"


def test_list_respects_limit(client):
    _seed(5)

    body = client.get("/meetings", params={"limit": 2}).json()

    assert [m["filename"] for m in body] == ["meeting-4.mp3", "meeting-3.mp3"]


def test_list_rejects_invalid_limit(client):
    assert client.get("/meetings", params={"limit": 0}).status_code == 422
    assert client.get("/meetings", params={"limit": 500}).status_code == 422


def test_uploaded_meeting_shows_up_in_list(client, no_background):
    upload = client.post(
        "/meetings/upload", files={"file": ("standup.mp3", b"audio" * 50, "audio/mpeg")}
    )

    body = client.get("/meetings").json()

    assert len(body) == 1
    assert body[0]["job_id"] == upload.json()["job_id"]
    assert body[0]["status"] == "processing"
