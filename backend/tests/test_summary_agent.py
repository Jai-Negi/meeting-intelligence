import asyncio
import json

import pytest

from app.agents import summary_agent
from app.agents.summary_agent import MAX_KEY_POINTS, SummaryAgent, SummaryData

VALID_REPLY = json.dumps(
    {
        "overview": "The team planned the launch and agreed to ship on Friday.",
        "key_points": ["Launch moves to Friday", "Sam owns the deck"],
    }
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
    instance = SummaryAgent()
    instance.retry_backoff_seconds = 0
    return instance


def _run(agent, transcript_text="We discussed the launch."):
    return asyncio.run(agent.execute(transcript_text=transcript_text))


def test_valid_reply_becomes_a_summary(agent, monkeypatch):
    monkeypatch.setattr(summary_agent, "generate_completion", _FakeLLM(VALID_REPLY))

    result = _run(agent)

    assert result.success
    assert result.data == SummaryData(
        overview="The team planned the launch and agreed to ship on Friday.",
        key_points=["Launch moves to Friday", "Sam owns the deck"],
    )


def test_reply_wrapped_in_code_fences_is_accepted(agent, monkeypatch):
    monkeypatch.setattr(summary_agent, "generate_completion", _FakeLLM(f"```json\n{VALID_REPLY}\n```"))

    result = _run(agent)

    assert result.success
    assert result.data.key_points == ["Launch moves to Friday", "Sam owns the deck"]


def test_prompt_contains_the_transcript(agent, monkeypatch):
    llm = _FakeLLM(VALID_REPLY)
    monkeypatch.setattr(summary_agent, "generate_completion", llm)

    _run(agent, transcript_text="We agreed to ship on Friday.")

    assert "We agreed to ship on Friday." in llm.calls[0]["prompt"]
    assert "never invent" in llm.calls[0]["system"].lower()


@pytest.mark.parametrize("key_points", [[], None])
def test_missing_or_empty_key_points_are_allowed(agent, monkeypatch, key_points):
    reply = json.dumps({"overview": "A short check in.", "key_points": key_points})
    monkeypatch.setattr(summary_agent, "generate_completion", _FakeLLM(reply))

    result = _run(agent)

    assert result.success
    assert result.data == SummaryData(overview="A short check in.", key_points=[])


def test_blank_and_non_text_key_points_are_skipped(agent, monkeypatch):
    reply = json.dumps({"overview": "Launch planning.", "key_points": ["Keep", "  ", 5, {"a": 1}, " Trim me "]})
    monkeypatch.setattr(summary_agent, "generate_completion", _FakeLLM(reply))

    result = _run(agent)

    assert result.success
    assert result.data.key_points == ["Keep", "Trim me"]


def test_key_points_are_capped(agent, monkeypatch):
    points = [f"Point {n}" for n in range(MAX_KEY_POINTS + 3)]
    reply = json.dumps({"overview": "A long meeting.", "key_points": points})
    monkeypatch.setattr(summary_agent, "generate_completion", _FakeLLM(reply))

    result = _run(agent)

    assert result.data.key_points == points[:MAX_KEY_POINTS]


@pytest.mark.parametrize(
    "bad_reply",
    [
        "this is not json at all",
        json.dumps(["a", "list"]),
        json.dumps({"key_points": ["No overview"]}),
        json.dumps({"overview": "   ", "key_points": []}),
        json.dumps({"overview": 5, "key_points": []}),
        json.dumps({"overview": "Fine", "key_points": "not a list"}),
    ],
)
def test_unusable_replies_fail_after_retrying(agent, monkeypatch, bad_reply):
    llm = _FakeLLM(bad_reply)
    monkeypatch.setattr(summary_agent, "generate_completion", llm)

    result = _run(agent)

    assert not result.success
    assert result.error
    assert len(llm.calls) == agent.max_retries


def test_a_bad_reply_followed_by_a_good_one_succeeds(agent, monkeypatch):
    llm = _FakeLLM("garbage", VALID_REPLY)
    monkeypatch.setattr(summary_agent, "generate_completion", llm)

    result = _run(agent)

    assert result.success
    assert len(llm.calls) == 2


def test_blank_transcript_is_rejected_without_calling_the_model(agent, monkeypatch):
    llm = _FakeLLM(VALID_REPLY)
    monkeypatch.setattr(summary_agent, "generate_completion", llm)

    result = _run(agent, transcript_text="   ")

    assert not result.success
    assert "no transcript text" in result.error
    assert llm.calls == []
