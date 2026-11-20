"""Errors shared across agents and tools."""


class PermanentError(Exception):
    """
    A failure that retrying cannot fix, such as a missing API key, a file
    that is too large, or a request the provider rejects as invalid. Agents
    stop at the first one instead of spending their retries on it.
    """


# 4xx responses that can succeed on a later attempt: request timeout,
# conflict, too early, and rate limiting.
_RETRYABLE_CLIENT_STATUSES = {408, 409, 425, 429}


def is_permanent_http_status(status_code: int) -> bool:
    """True for client errors that will fail the same way however often they are retried."""
    return 400 <= status_code < 500 and status_code not in _RETRYABLE_CLIENT_STATUSES
