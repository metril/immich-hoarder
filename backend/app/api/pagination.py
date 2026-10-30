import base64
import binascii
import enum
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

MAX_LIMIT = 200
DEFAULT_LIMIT = 50


class Page[T](BaseModel):
    items: list[T] = Field(description="The page of results.")
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for the next page; pass it as `cursor`. Null on the last page.",
        examples=["MTIz"],
    )


def encode_cursor(last_id: int) -> str:
    return base64.urlsafe_b64encode(str(last_id).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, binascii.Error):
        raise HTTPException(422, "invalid cursor") from None


SORT_DESCRIPTION = (
    "Sort order. A leading `-` sorts descending. `id` is always the final tiebreak. "
    "A cursor is only valid with the sort it was issued for (otherwise 400)."
)
Q_DESCRIPTION = "Case-insensitive substring filter (matches the listed text fields)."


def apply_q(stmt: Select[Any], q: str | None, *cols: Any) -> Select[Any]:
    """Filter by case-insensitive substring across the given columns (LIKE-escaped)."""
    term = (q or "").strip()
    if not term:
        return stmt
    return stmt.where(or_(*(c.icontains(term, autoescape=True) for c in cols)))


def _enc(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _to_json(v: Any) -> Any:
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _from_json(col: Any, v: Any) -> Any:
    try:
        py = col.type.python_type
        if issubclass(py, datetime):
            return datetime.fromisoformat(v)
        if issubclass(py, enum.Enum):
            return py(v)
    except (NotImplementedError, ValueError, TypeError):
        raise HTTPException(422, "invalid cursor") from None
    return v


def _is_datetime(col: Any) -> bool:
    try:
        return bool(issubclass(col.type.python_type, datetime))
    except NotImplementedError:
        return False


def _decode_composite(cursor: str, sort: str) -> tuple[Any, int]:
    try:
        d = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if not isinstance(d, dict):
            raise ValueError
        c_sort, v, i = d["sort"], d["v"], int(d["id"])
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise HTTPException(422, "invalid cursor") from None
    if c_sort != sort:
        raise HTTPException(400, "cursor does not match the requested sort")
    return v, i


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    cursor: str | None,
    limit: int = DEFAULT_LIMIT,
    desc: bool = False,
    sort: str | None = None,
    sort_cols: Mapping[str, Any] | None = None,
) -> tuple[list[Any], str | None]:
    """Keyset pagination. Default: on `id` with a bare-int cursor.

    With `sort` (e.g. "name" / "-name"), orders by `sort_cols[field]` (a NOT NULL column) then
    `id` in the same direction; the cursor encodes `{sort, v, id}`.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    id_col = stmt.column_descriptions[0]["entity"].id
    if sort is None:
        if cursor:
            try:
                after = decode_cursor(cursor)
            except HTTPException:
                _decode_composite(cursor, "")  # composite cursor -> 400; garbage -> 422
                raise
            stmt = stmt.where(id_col < after if desc else id_col > after)
        order = id_col.desc() if desc else id_col
        rows = list((await session.execute(stmt.order_by(order).limit(limit + 1))).scalars())
        if len(rows) > limit:
            rows = rows[:limit]
            return rows, encode_cursor(rows[-1].id)
        return rows, None

    field = sort.lstrip("-")
    desc = sort.startswith("-")
    cols = {"id": id_col, **(sort_cols or {})}
    if field not in cols:
        raise HTTPException(422, "invalid sort")
    col = cols[field]
    # SQLite stores CURRENT_TIMESTAMP without fractional seconds but binds datetimes with
    # them, so equality ties never match; compare on whole seconds there (id breaks ties).
    sqlite_ts = (
        field != "id"
        and _is_datetime(col)
        and session.sync_session.get_bind().dialect.name == "sqlite"
    )
    key = func.datetime(col) if sqlite_ts else col
    if cursor:
        try:  # a bare-int cursor belongs to the default sort only
            decode_cursor(cursor)
        except HTTPException:
            pass
        else:
            raise HTTPException(400, "cursor does not match the requested sort")
        v, i = _decode_composite(cursor, sort)
        if field == "id":
            stmt = stmt.where(id_col < i if desc else id_col > i)
        else:
            v = v if sqlite_ts and isinstance(v, str) else _from_json(col, v)
            if desc:
                stmt = stmt.where(or_(key < v, and_(key == v, id_col < i)))
            else:
                stmt = stmt.where(or_(key > v, and_(key == v, id_col > i)))
    order_by = [key, id_col] if field != "id" else [id_col]
    if desc:
        order_by = [c.desc() for c in order_by]
    rows = list((await session.execute(stmt.order_by(*order_by).limit(limit + 1))).scalars())
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        v = None if field == "id" else _to_json(getattr(last, col.key))
        if sqlite_ts:
            v = getattr(last, col.key).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        return rows, _enc({"sort": sort, "v": v, "id": last.id})
    return rows, None
