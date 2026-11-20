import asyncio

import pytest

from app.agents import base_agent
from app.agents.base_agent import BaseAgent
from app.errors import PermanentError


class _ScriptedAgent(BaseAgent):
    """Raises or returns whatever its script says, one step per attempt."""

    name = "scripted_agent"
    max_retries = 3
    timeout_seconds = 1
    retry_backoff_seconds = 0

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = 0

    async def run(self, **kwargs):
        self.calls += 1
        step = self.steps[min(self.calls, len(self.steps)) - 1]
        if step == "hang":
            await asyncio.sleep(10)
        if isinstance(step, Exception):
            raise step
        return step


def _execute(agent):
    return asyncio.run(agent.execute())


def test_success_on_the_first_attempt():
    agent = _ScriptedAgent("done")

    result = _execute(agent)

    assert result.success
    assert result.data == "done"
    assert result.attempts == 1


def test_a_temporary_error_is_retried_until_it_succeeds():
    agent = _ScriptedAgent(RuntimeError("blip"), "done")

    result = _execute(agent)

    assert result.success
    assert result.attempts == 2
    assert agent.calls == 2


def test_temporary_errors_use_every_attempt_then_report_the_last_error():
    agent = _ScriptedAgent(RuntimeError("first"), RuntimeError("second"), RuntimeError("third"))

    result = _execute(agent)

    assert not result.success
    assert result.error == "third"
    assert result.attempts == 3


def test_a_permanent_error_stops_at_once():
    agent = _ScriptedAgent(PermanentError("api key is not set"), "done")

    result = _execute(agent)

    assert not result.success
    assert result.error == "api key is not set"
    assert result.attempts == 1
    assert agent.calls == 1


def test_a_missing_file_stops_at_once():
    agent = _ScriptedAgent(FileNotFoundError("audio file not found"), "done")

    result = _execute(agent)

    assert not result.success
    assert agent.calls == 1


def test_a_timeout_is_retried_by_default():
    agent = _ScriptedAgent("hang", "done")
    agent.timeout_seconds = 0.05

    result = _execute(agent)

    assert result.success
    assert agent.calls == 2


def test_a_timeout_is_not_retried_when_the_agent_opts_out():
    agent = _ScriptedAgent("hang", "done")
    agent.timeout_seconds = 0.05
    agent.retry_on_timeout = False

    result = _execute(agent)

    assert not result.success
    assert "timed out" in result.error
    assert agent.calls == 1


@pytest.mark.parametrize("jitter", [0.5, 1.0])
def test_backoff_doubles_each_attempt_within_the_jitter_range(monkeypatch, jitter):
    monkeypatch.setattr(base_agent.random, "uniform", lambda low, high: jitter)
    agent = _ScriptedAgent("done")
    agent.retry_backoff_seconds = 2.0

    delays = [agent._backoff_delay(attempt) for attempt in (1, 2, 3)]

    assert delays == [2.0 * jitter, 4.0 * jitter, 8.0 * jitter]


def test_jitter_is_drawn_from_half_to_the_full_delay(monkeypatch):
    seen = []

    def fake_uniform(low, high):
        seen.append((low, high))
        return high

    monkeypatch.setattr(base_agent.random, "uniform", fake_uniform)
    _ScriptedAgent("done")._backoff_delay(1)

    assert seen == [(0.5, 1.0)]
