import base64
import binascii
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_LIMIT = 200
DEFAULT_LIMIT = 50


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


def encode_cursor(last_id: int) -> str:
    return base64.urlsafe_b64encode(str(last_id).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, binascii.Error):
        raise HTTPException(422, "invalid cursor") from None


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    cursor: str | None,
    limit: int = DEFAULT_LIMIT,
    desc: bool = False,
) -> tuple[list[Any], str | None]:
    """Keyset pagination on the primary-key `id` of the statement's first entity."""
    limit = max(1, min(limit, MAX_LIMIT))
    id_col = stmt.column_descriptions[0]["entity"].id
    if cursor:
        after = decode_cursor(cursor)
        stmt = stmt.where(id_col < after if desc else id_col > after)
    order = id_col.desc() if desc else id_col
    rows = list((await session.execute(stmt.order_by(order).limit(limit + 1))).scalars())
    if len(rows) > limit:
        rows = rows[:limit]
        return rows, encode_cursor(rows[-1].id)
    return rows, None
