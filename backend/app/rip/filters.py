"""Per-source filters: validation, gallery-dl option mapping and post-download checks."""

import re
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models import BackfillMode
from app.rip.media import MediaInfo

INCREMENTAL_SKIP = "abort:20"
_TITLE_MAX = 1000


class FilterSpec(BaseModel, extra="forbid"):
    min_width: int | None = Field(default=None, ge=0)
    min_height: int | None = Field(default=None, ge=0)
    min_bytes: int | None = Field(default=None, ge=0)
    max_bytes: int | None = Field(default=None, ge=0)
    aspect_min: float | None = Field(default=None, ge=0)
    aspect_max: float | None = Field(default=None, ge=0)
    title_include: str | None = Field(default=None, max_length=200)
    title_exclude: str | None = Field(default=None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    max_items: int | None = Field(default=None, ge=1)
    phash_distance: int | None = Field(default=3, ge=0, le=3)

    @field_validator("title_include", "title_exclude")
    @classmethod
    def _regex(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"invalid regex: {e}") from None
        return v

    @model_validator(mode="after")
    def _consistent(self) -> "FilterSpec":
        for lo, hi in (
            ("min_bytes", "max_bytes"),
            ("aspect_min", "aspect_max"),
            ("date_from", "date_to"),
        ):
            a, b = getattr(self, lo), getattr(self, hi)
            if a is not None and b is not None and a > b:
                raise ValueError(f"{lo} must be <= {hi}")
        return self


def validate_backfill(mode: BackfillMode, value: str | None) -> None:
    """Raise ValueError when `value` does not fit `mode`."""
    if mode == BackfillMode.full:
        if value is not None:
            raise ValueError("backfill_value must be empty for full backfill")
    elif mode == BackfillMode.last_n:
        if value is None or not value.isascii() or not value.isdigit() or int(value) < 1:
            raise ValueError("backfill_value must be an integer >= 1 for last_n")
    elif value is None:
        raise ValueError("backfill_value must be an ISO date for since")
    else:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("backfill_value must be an ISO date for since") from None


def gdl_filter_options(
    spec: FilterSpec, backfill_mode: BackfillMode, backfill_value: str | None, incremental: bool
) -> dict[str, dict[str, Any]]:
    """Return gallery-dl options split by config section."""
    o: dict[str, Any] = {}
    d: dict[str, Any] = {}
    if spec.min_bytes is not None:
        d["filesize-min"] = spec.min_bytes
    if spec.max_bytes is not None:
        d["filesize-max"] = spec.max_bytes
    date_min = spec.date_from
    limits: list[int] = []
    if not incremental:
        if backfill_mode == BackfillMode.last_n and backfill_value:
            limits.append(int(backfill_value))
        elif backfill_mode == BackfillMode.since and backfill_value:
            since = date.fromisoformat(backfill_value)
            date_min = max(since, date_min) if date_min else since
    if spec.max_items is not None:
        limits.append(spec.max_items)
    if date_min is not None:
        o["date-min"] = date_min.isoformat()
    if spec.date_to is not None:
        o["date-max"] = f"{spec.date_to.isoformat()}T23:59:59"
    if limits:
        o["post-range"] = f"1-{min(limits)}"
    if incremental:
        o["skip"] = INCREMENTAL_SKIP
    return {"extractor": o, "downloader": d}


def _day(d: Any) -> date | None:
    if not isinstance(d, datetime):
        return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC).date()


def check(
    info: MediaInfo,
    meta: dict[str, Any],
    spec: FilterSpec,
    allow_animated: bool,
    *,
    since: date | None = None,
) -> str | None:
    """`since` is the effective first-run lower bound (few extractors honour date-min)."""
    if info.animated and not allow_animated:
        return "animated"
    if (spec.min_width and info.width < spec.min_width) or (
        spec.min_height and info.height < spec.min_height
    ):
        return "too_small"
    if spec.max_bytes is not None and info.size > spec.max_bytes:
        return "too_large_bytes"
    if spec.min_bytes is not None and info.size < spec.min_bytes:
        return "too_small_bytes"
    ratio = info.width / info.height if info.height else 0.0
    if (spec.aspect_min is not None and ratio < spec.aspect_min) or (
        spec.aspect_max is not None and ratio > spec.aspect_max
    ):
        return "aspect"
    return check_meta(meta, spec, since=since)


def check_meta(meta: dict[str, Any], spec: FilterSpec, *, since: date | None = None) -> str | None:
    """Pre-download checks (title and date) that need only extractor metadata."""
    title = str(meta.get("title") or meta.get("filename") or "")[:_TITLE_MAX]
    if spec.title_exclude and re.search(spec.title_exclude, title, re.IGNORECASE):
        return "title_excluded"
    if spec.title_include and not re.search(spec.title_include, title, re.IGNORECASE):
        return "title_not_included"
    day = _day(meta.get("date"))
    if day is not None and (
        (spec.date_from and day < spec.date_from)
        or (spec.date_to and day > spec.date_to)
        or (since and day < since)
    ):
        return "date_out_of_range"
    return None
