import json
import logging
from dataclasses import dataclass

from app.agents.base_agent import AgentError, BaseAgent
from app.tools.llm_tool import generate_completion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You write follow up emails after meetings.

You are given the meeting transcript, plus the action items and decisions that were already extracted from it. Write a short, clear, professional email that the person who ran the meeting could send to the attendees.

Rules:
- Only use facts that appear in the transcript, the action items or the decisions. Never invent names, dates, numbers or commitments.
- Start with a one line greeting such as "Hi all,".
- Give a two or three sentence summary of what the meeting covered.
- If there are decisions, list them under a line that says "Decisions".
- If there are action items, list each one under a line that says "Action items", with the owner and due date when they are known.
- End with a brief closing and the sign off "[Your name]".
- Use plain text only. No markdown, no bold, no bullet symbols other than a simple dash.
- Keep it under 250 words.

Respond with ONLY a JSON object, no commentary and no code fences, in exactly this shape:
{"subject": "short subject line", "body": "the full email body"}"""


class EmailAgentError(AgentError):
    """Raised when the model's reply cannot be turned into an email draft."""


@dataclass
class EmailDraft:
    subject: str
    body: str


def _format_action_items(action_items: list[dict]) -> str:
    if not action_items:
        return "None recorded."

    lines = []
    for item in action_items:
        details = [part for part in (item.get("owner"), item.get("due_date")) if part]
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"- {item['description']}{suffix}")
    return "\n".join(lines)


def _format_decisions(decisions: list[dict]) -> str:
    if not decisions:
        return "None recorded."

    lines = []
    for item in decisions:
        context = f" ({item['context']})" if item.get("context") else ""
        lines.append(f"- {item['decision']}{context}")
    return "\n".join(lines)


class EmailAgent(BaseAgent):
    name = "email_agent"
    max_retries = 3
    timeout_seconds = 90

    async def run(
        self,
        transcript_text: str,
        action_items: list[dict] | None = None,
        decisions: list[dict] | None = None,
    ) -> EmailDraft:
        if not transcript_text or not transcript_text.strip():
            raise EmailAgentError("there is no transcript text to write an email from")

        prompt = (
            f"Transcript:\n{transcript_text}\n\n"
            f"Action items:\n{_format_action_items(action_items or [])}\n\n"
            f"Decisions:\n{_format_decisions(decisions or [])}"
        )

        raw = await generate_completion(prompt=prompt, system=SYSTEM_PROMPT)
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> EmailDraft:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise EmailAgentError(f"the model did not return valid JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise EmailAgentError("the model returned JSON that was not an object")

        subject = parsed.get("subject")
        body = parsed.get("body")
        if not isinstance(subject, str) or not subject.strip():
            raise EmailAgentError("the model's reply had no subject")
        if not isinstance(body, str) or not body.strip():
            raise EmailAgentError("the model's reply had no body")

        return EmailDraft(subject=subject.strip(), body=body.strip())
