import json
import logging
from dataclasses import dataclass
from typing import Any

from app.agents.base_agent import BaseAgent
from app.tools.llm_tool import generate_completion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You extract decisions that were made during a meeting from its transcript. "
    "A decision is something the group agreed on or committed to, not just a "
    "topic that was discussed without a clear conclusion. "
    "Respond with only a JSON array, no other text. "
    "Each item must have exactly these fields: "
    '"decision" (string, required, a clear statement of what was decided), '
    '"context" (string or null, one sentence on why this decision was made, '
    "if that is clear from the transcript). "
    "If no clear decisions were made, respond with an empty array: []"
)


@dataclass
class DecisionData:
    decision: str
    context: str | None


class DecisionAgentError(Exception):
    pass


class DecisionAgent(BaseAgent):
    """
    Reads a meeting transcript and extracts the concrete decisions that
    were made, as distinct from topics that were merely discussed. This
    is the difference between "we talked about pricing" and
    "we decided to raise prices by 10 percent next quarter".
    """

    name = "decision_agent"
    max_retries = 3
    timeout_seconds = 90
    retry_backoff_seconds = 3.0

    async def run(self, transcript_text: str, **kwargs: Any) -> list[DecisionData]:
        prompt = f"Transcript:\n\n{transcript_text}\n\nExtract the decisions as a JSON array."

        raw_response = await generate_completion(prompt=prompt, system=SYSTEM_PROMPT)

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> list[DecisionData]:
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
                "failed to parse decision response as json",
                extra={"raw_response": raw_response[:200]},
            )
            raise DecisionAgentError(f"could not parse LLM response as JSON: {exc}") from exc

        if not isinstance(parsed, list):
            raise DecisionAgentError("expected a JSON array of decisions")

        decisions = []
        for entry in parsed:
            if not isinstance(entry, dict) or "decision" not in entry:
                logger.warning("skipping malformed decision entry", extra={"entry": str(entry)[:200]})
                continue

            decisions.append(
                DecisionData(
                    decision=entry["decision"],
                    context=entry.get("context"),
                )
            )

        return decisions
