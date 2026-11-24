import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.base_agent import AgentError, BaseAgent
from app.tools.llm_tool import generate_completion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You summarise meetings from their transcripts. "
    "Respond with only a JSON object, no other text, in exactly this shape: "
    '{"overview": "...", "key_points": ["...", "..."]}. '
    '"overview" (string, required) is two to four sentences on what the meeting '
    "was about and where it ended up. "
    '"key_points" (array of strings) lists the most important points raised, '
    "at most six, each one short sentence. "
    "Only use what is said in the transcript. Never invent names, numbers, dates "
    "or outcomes. If the transcript is too short to have key points, use an "
    "empty array."
)

MAX_KEY_POINTS = 6


@dataclass
class SummaryData:
    overview: str
    key_points: list[str] = field(default_factory=list)


class SummaryAgentError(AgentError):
    """Raised when the model's reply cannot be turned into a summary."""


class SummaryAgent(BaseAgent):
    """
    Reads a meeting transcript and writes a short overview plus a list of
    key points, so someone can understand the meeting at a glance before
    looking at the action items, decisions or full transcript.
    """

    name = "summary_agent"
    max_retries = 3
    timeout_seconds = 90
    retry_backoff_seconds = 3.0

    async def run(self, transcript_text: str, **kwargs: Any) -> SummaryData:
        if not transcript_text or not transcript_text.strip():
            raise SummaryAgentError("there is no transcript text to summarise")

        prompt = f"Transcript:\n\n{transcript_text}\n\nSummarise the meeting as a JSON object."

        raw_response = await generate_completion(prompt=prompt, system=SYSTEM_PROMPT)

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> SummaryData:
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
                "failed to parse summary response as json",
                extra={"raw_response": raw_response[:200]},
            )
            raise SummaryAgentError(f"could not parse LLM response as JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise SummaryAgentError("expected a JSON object with an overview and key points")

        overview = parsed.get("overview")
        if not isinstance(overview, str) or not overview.strip():
            raise SummaryAgentError("the model's reply had no overview")

        raw_points = parsed.get("key_points") or []
        if not isinstance(raw_points, list):
            raise SummaryAgentError("expected key_points to be a JSON array")

        key_points = []
        for point in raw_points:
            if not isinstance(point, str) or not point.strip():
                logger.warning("skipping malformed key point", extra={"entry": str(point)[:200]})
                continue
            key_points.append(point.strip())

        return SummaryData(overview=overview.strip(), key_points=key_points[:MAX_KEY_POINTS])
