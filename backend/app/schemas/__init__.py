from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def _as_utc(dt: datetime) -> datetime:
    """DB datetimes are naive UTC; tag them so JSON carries an offset."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
