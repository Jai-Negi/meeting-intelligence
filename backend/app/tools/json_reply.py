import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# How many possible starting brackets to try before giving up, so a long
# reply full of stray brackets cannot make parsing slow.
_MAX_START_ATTEMPTS = 20


class JSONReplyError(ValueError):
    """Raised when no JSON value can be found in a model's reply."""


def parse_json_reply(raw: str) -> Any:
    """
    Pulls the JSON value out of a model's reply.

    Models are told to answer with JSON only, but they sometimes wrap it in a
    markdown code fence or put a sentence before or after it. This accepts
    all of those: it reads the inside of a code fence if there is one, tries
    the whole text as JSON, and otherwise decodes from the first opening
    bracket or brace that starts a valid JSON value. Checking that the value
    has the right shape is left to each agent.
    """
    text = (raw or "").strip()

    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    # RecursionError comes from very deeply nested brackets, which the
    # standard decoder cannot handle. That is never a usable reply.
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        pass

    decoder = json.JSONDecoder()
    starts = [i for i, char in enumerate(text) if char in "[{"][:_MAX_START_ATTEMPTS]
    for start in starts:
        try:
            value, _ = decoder.raw_decode(text, start)
            return value
        except (json.JSONDecodeError, RecursionError):
            continue

    raise JSONReplyError(f"no JSON found in the reply: {text[:80]!r}")
