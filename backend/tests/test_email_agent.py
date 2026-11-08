import asyncio
import json

import pytest

from app.agents import email_agent
from app.agents.email_agent import EmailAgent, EmailDraft

VALID_REPLY = json.dumps(
    {"subject": "Follow up: launch planning", "body": "Hi all,\n\nThanks for joining.\n\n[Your name]"}
)


class _FakeLLM:
    """Stands in for generate_completion and records how it was called."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def __call__(self, prompt, system=None):
        self.calls.append({"prompt": prompt, "system": system})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def agent():
    instance = EmailAgent()
    instance.retry_backoff_seconds = 0
    return instance


def _run(agent, **kwargs):
    return asyncio.run(agent.execute(**kwargs))


def test_valid_reply_becomes_an_email_draft(agent, monkeypatch):
    monkeypatch.setattr(email_agent, "generate_completion", _FakeLLM(VALID_REPLY))

    result = _run(agent, transcript_text="We discussed the launch.")

    assert result.success
    assert result.data == EmailDraft(
        subject="Follow up: launch planning",
        body="Hi all,\n\nThanks for joining.\n\n[Your name]",
    )


def test_reply_wrapped_in_code_fences_is_accepted(agent, monkeypatch):
    monkeypatch.setattr(email_agent, "generate_completion", _FakeLLM(f"```json\n{VALID_REPLY}\n```"))

    result = _run(agent, transcript_text="We discussed the launch.")

    assert result.success
    assert result.data.subject == "Follow up: launch planning"


def test_prompt_contains_transcript_action_items_and_decisions(agent, monkeypatch):
    llm = _FakeLLM(VALID_REPLY)
    monkeypatch.setattr(email_agent, "generate_completion", llm)

    _run(
        agent,
        transcript_text="We agreed to ship on Friday.",
        action_items=[
            {"description": "Send the deck", "owner": "Sam", "due_date": "Friday"},
            {"description": "Book the room", "owner": None, "due_date": None},
        ],
        decisions=[{"decision": "Ship on Friday", "context": "the team agreed"}],
    )

    prompt = llm.calls[0]["prompt"]
    assert "We agreed to ship on Friday." in prompt
    assert "- Send the deck (Sam, Friday)" in prompt
    assert "- Book the room" in prompt
    assert "- Ship on Friday (the team agreed)" in prompt
    assert "email" in llm.calls[0]["system"].lower()


def test_missing_action_items_and_decisions_are_described_as_none(agent, monkeypatch):
    llm = _FakeLLM(VALID_REPLY)
    monkeypatch.setattr(email_agent, "generate_completion", llm)

    _run(agent, transcript_text="Short chat.")

    prompt = llm.calls[0]["prompt"]
    assert "Action items:\nNone recorded." in prompt
    assert "Decisions:\nNone recorded." in prompt


@pytest.mark.parametrize(
    "bad_reply",
    [
        "this is not json at all",
        json.dumps(["a", "list"]),
        json.dumps({"subject": "Only a subject"}),
        json.dumps({"body": "Only a body"}),
        json.dumps({"subject": "   ", "body": "Blank subject"}),
        json.dumps({"subject": "Blank body", "body": ""}),
        json.dumps({"subject": 5, "body": "Subject is not text"}),
    ],
)
def test_unusable_replies_fail_after_retrying(agent, monkeypatch, bad_reply):
    llm = _FakeLLM(bad_reply)
    monkeypatch.setattr(email_agent, "generate_completion", llm)

    result = _run(agent, transcript_text="We discussed the launch.")

    assert not result.success
    assert result.error
    assert len(llm.calls) == agent.max_retries


def test_a_bad_reply_followed_by_a_good_one_succeeds(agent, monkeypatch):
    llm = _FakeLLM("garbage", VALID_REPLY)
    monkeypatch.setattr(email_agent, "generate_completion", llm)

    result = _run(agent, transcript_text="We discussed the launch.")

    assert result.success
    assert len(llm.calls) == 2


def test_a_failing_llm_call_is_reported_not_raised(agent, monkeypatch):
    monkeypatch.setattr(email_agent, "generate_completion", _FakeLLM(RuntimeError("groq is down")))

    result = _run(agent, transcript_text="We discussed the launch.")

    assert not result.success
    assert "groq is down" in result.error


def test_blank_transcript_is_rejected_without_calling_the_model(agent, monkeypatch):
    llm = _FakeLLM(VALID_REPLY)
    monkeypatch.setattr(email_agent, "generate_completion", llm)

    result = _run(agent, transcript_text="   ")

    assert not result.success
    assert "no transcript text" in result.error
    assert llm.calls == []
