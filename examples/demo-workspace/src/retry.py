"""Credential-free demo retry policy."""

MAX_RETRIES = 3
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def should_retry(status_code: int, attempt: int) -> bool:
    """Return whether a safe request may be attempted again."""

    return status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES
