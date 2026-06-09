import email.utils
import random
from datetime import datetime, timezone

MAX_RETRY_AFTER_SECS = 30.0


def calculate_backoff(attempt: int) -> float:
    """Calculates exponential backoff with jitter matching the TS implementation.

    The base is 250ms doubled each attempt, capped at 8 seconds.
    Jitter is applied in the range [50%, 100%] of the base.
    """
    base = min(0.250 * (2**attempt), 8.0)
    # Match TS jitter: base * (0.5 + random * 0.5)
    return float(base * (0.5 + random.random() * 0.5))


def parse_retry_after(header: str | None) -> float | None:
    """Parses a Retry-After header.

    Supports both delta-seconds (e.g. "5") and HTTP-date strings.
    Clamps the result between 0 and 30 seconds.
    """
    if not header:
        return None

    header = header.strip()
    try:
        seconds = float(header)
        return min(max(0.0, seconds), MAX_RETRY_AFTER_SECS)
    except ValueError:
        pass

    try:
        dt = email.utils.parsedate_to_datetime(header)
        # Ensure timezone comparison (parsedate_to_datetime returns timezone aware)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (dt - datetime.now(timezone.utc)).total_seconds()
        return min(max(0.0, delta), MAX_RETRY_AFTER_SECS)
    except Exception:
        return None
