from datetime import UTC, datetime

from croniter import croniter


def validate_cron(v: str) -> str:
    """Require 5 fields or an @alias, and at least one reachable date."""
    t = v.strip()
    if not t.startswith("@") and len(t.split()) != 5:
        raise ValueError("invalid cron expression")
    try:
        if not croniter.is_valid(t):
            raise ValueError("invalid cron expression")
        croniter(t, datetime.now(UTC)).get_next(datetime)
    except ValueError as e:  # croniter bad-date errors subclass ValueError
        raise ValueError("invalid cron expression") from e
    return v
