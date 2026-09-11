import json
import logging
from dataclasses import dataclass
from typing import Any

from app.agents.base_agent import BaseAgent
from app.tools.llm_tool import generate_completion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You extract action items from meeting transcripts. "
    "Respond with only a JSON array, no other text. "
    "Each item must have exactly these fields: "
    '"description" (string, required), "owner" (string or null), '
    '"due_date" (string or null, use the format mentioned in the transcript '
    "as is, do not invent a date if none is mentioned). "
    "If there are no action items, respond with an empty array: []"
)


@dataclass
class ActionItemData:
    description: str
    owner: str | None
    due_date: str | None


class ActionItemAgentError(Exception):
    pass


class ActionItemAgent(BaseAgent):
    """
    Reads a meeting transcript and extracts a structured list of
    action items using an LLM. Downstream, each item gets written to
    the action_items table against the originating meeting.
    """

    name = "action_item_agent"
    max_retries = 3
    timeout_seconds = 90
    retry_backoff_seconds = 3.0

    async def run(self, transcript_text: str, **kwargs: Any) -> list[ActionItemData]:
        prompt = f"Transcript:\n\n{transcript_text}\n\nExtract the action items as a JSON array."

        raw_response = await generate_completion(prompt=prompt, system=SYSTEM_PROMPT)

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> list[ActionItemData]:
        cleaned = raw_response.strip()

        # Models sometimes wrap JSON in markdown code fences despite being told not to.
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(
                "failed to parse action item response as json",
                extra={"raw_response": raw_response[:200]},
            )
            raise ActionItemAgentError(f"could not parse LLM response as JSON: {exc}") from exc

        if not isinstance(parsed, list):
            raise ActionItemAgentError("expected a JSON array of action items")

        items = []
        for entry in parsed:
            if not isinstance(entry, dict) or "description" not in entry:
                logger.warning("skipping malformed action item entry", extra={"entry": str(entry)[:200]})
                continue

            items.append(
                ActionItemData(
                    description=entry["description"],
                    owner=entry.get("owner"),
                    due_date=entry.get("due_date"),
                )
            )

        return items
