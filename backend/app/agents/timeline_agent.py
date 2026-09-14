import json
import logging
from dataclasses import dataclass
from typing import Any

from app.agents.base_agent import BaseAgent
from app.tools.llm_tool import generate_completion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You extract a timeline of topics discussed from a meeting transcript. "
    "Respond with only a JSON array, no other text. "
    "Each item must have exactly these fields: "
    '"topic" (string, required, a short label for what was being discussed), '
    '"summary" (string, required, one or two sentences on what was said about it), '
    '"approx_time" (string or null, a rough timestamp or position in the meeting '
    "if it is clear from the transcript, such as \"early in the meeting\" or an "
    "actual timestamp if one is present, otherwise null). "
    "List items in the order they occurred. "
    "If the transcript has no clear distinct topics, respond with an empty array: []"
)


@dataclass
class TimelineEventData:
    topic: str
    summary: str
    approx_time: str | None


class TimelineAgentError(Exception):
    pass


class TimelineAgent(BaseAgent):
    """
    Reads a meeting transcript and produces an ordered timeline of the
    topics discussed, so someone can see the shape of the meeting
    without reading the full transcript.
    """

    name = "timeline_agent"
    max_retries = 3
    timeout_seconds = 90
    retry_backoff_seconds = 3.0

    async def run(self, transcript_text: str, **kwargs: Any) -> list[TimelineEventData]:
        prompt = f"Transcript:\n\n{transcript_text}\n\nExtract the timeline as a JSON array."

        raw_response = await generate_completion(prompt=prompt, system=SYSTEM_PROMPT)

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> list[TimelineEventData]:
        cleaned = raw_response.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(
                "failed to parse timeline response as json",
                extra={"raw_response": raw_response[:200]},
            )
            raise TimelineAgentError(f"could not parse LLM response as JSON: {exc}") from exc

        if not isinstance(parsed, list):
            raise TimelineAgentError("expected a JSON array of timeline events")

        events = []
        for entry in parsed:
            if not isinstance(entry, dict) or "topic" not in entry or "summary" not in entry:
                logger.warning("skipping malformed timeline entry", extra={"entry": str(entry)[:200]})
                continue

            events.append(
                TimelineEventData(
                    topic=entry["topic"],
                    summary=entry["summary"],
                    approx_time=entry.get("approx_time"),
                )
            )

        return events
