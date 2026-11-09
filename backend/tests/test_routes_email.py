import json
from types import SimpleNamespace

from app.agents import email_agent
from app.api import routes_email
from app.database.models import ActionItem, Decision, Meeting, Transcript
from app.database.session import SessionLocal


def _seed_meeting(status: str = "completed", with_transcript: bool = True, job_id: str = "job-1") -> str:
    db = SessionLocal()
    try:
        db.add(Meeting(id=job_id, filename="standup.mp3", file_path="x", status=status))
        db.flush()
        if with_transcript:
            db.add(Transcript(meeting_id=job_id, text="We agreed to ship on Friday.", language="en"))
            db.add(ActionItem(meeting_id=job_id, description="Send the deck", owner="Sam", due_date="Friday"))
            db.add(Decision(meeting_id=job_id, decision="Ship on Friday", context="the team agreed"))
        db.commit()
    finally:
        db.close()
    return job_id


def _fake_email_agent(result, calls):
    class _Agent:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return result

    return _Agent


def test_completed_meeting_gets_a_drafted_email(client, monkeypatch):
    job_id = _seed_meeting()
    calls = []
    draft = SimpleNamespace(subject="Follow up: launch", body="Hi all,\n\nWe ship Friday.")
    monkeypatch.setattr(
        routes_email, "EmailAgent", _fake_email_agent(SimpleNamespace(success=True, data=draft), calls)
    )

    response = client.post(f"/meetings/{job_id}/email")

    assert response.status_code == 200
    assert response.json() == {"subject": "Follow up: launch", "body": "Hi all,\n\nWe ship Friday."}
    assert calls == [
        {
            "transcript_text": "We agreed to ship on Friday.",
            "action_items": [{"description": "Send the deck", "owner": "Sam", "due_date": "Friday"}],
            "decisions": [{"decision": "Ship on Friday", "context": "the team agreed"}],
        }
    ]


def test_real_agent_is_wired_through_to_the_language_model(client, monkeypatch):
    job_id = _seed_meeting()
    prompts = []

    async def fake_llm(prompt, system=None):
        prompts.append(prompt)
        return json.dumps({"subject": "Follow up", "body": "Hi all,\n\n[Your name]"})

    monkeypatch.setattr(email_agent, "generate_completion", fake_llm)

    response = client.post(f"/meetings/{job_id}/email")

    assert response.status_code == 200
    assert response.json()["subject"] == "Follow up"
    assert "Send the deck (Sam, Friday)" in prompts[0]
    assert "Ship on Friday" in prompts[0]


def test_unknown_job_returns_404_without_calling_the_agent(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes_email, "EmailAgent", _fake_email_agent(None, calls))

    assert client.post("/meetings/does-not-exist/email").status_code == 404
    assert calls == []


def test_unfinished_or_failed_meetings_are_refused_without_calling_the_agent(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes_email, "EmailAgent", _fake_email_agent(None, calls))
    # a meeting that is still being analysed already has its transcript saved,
    # so the status alone has to be what stops a half finished draft
    _seed_meeting(status="processing", with_transcript=True, job_id="busy")
    _seed_meeting(status="failed", with_transcript=True, job_id="broken")

    for job_id in ("busy", "broken"):
        response = client.post(f"/meetings/{job_id}/email")
        assert response.status_code == 409
        assert "not finished processing" in response.json()["detail"]
    assert calls == []


def test_completed_meeting_without_a_transcript_is_refused(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes_email, "EmailAgent", _fake_email_agent(None, calls))
    job_id = _seed_meeting(status="completed", with_transcript=False)

    assert client.post(f"/meetings/{job_id}/email").status_code == 409
    assert calls == []


def test_agent_failure_becomes_a_502_with_the_reason(client, monkeypatch):
    job_id = _seed_meeting()
    failed = SimpleNamespace(success=False, data=None, error="the model did not return valid JSON")
    monkeypatch.setattr(routes_email, "EmailAgent", _fake_email_agent(failed, []))

    response = client.post(f"/meetings/{job_id}/email")

    assert response.status_code == 502
    assert "could not draft the email" in response.json()["detail"]
    assert "did not return valid JSON" in response.json()["detail"]
