from string import Formatter
from typing import Any

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.extractors import validate_gdl_options
from app.db.models import BackfillMode, Source, Visibility

ALBUM_FIELDS = frozenset({"subreddit", "author", "user", "site", "category", "source", "date"})


def check_cron(v: str | None) -> str | None:
    if v is not None and not croniter.is_valid(v):
        raise ValueError("invalid cron expression")
    return v


def check_template(v: str | None) -> str | None:
    if v is None:
        return v
    try:
        names = {f.split(".")[0].split("[")[0] for _, f, _, _ in Formatter().parse(v) if f}
    except ValueError as e:
        raise ValueError(f"invalid album template: {e}") from None
    if bad := names - ALBUM_FIELDS:
        raise ValueError(f"unknown album template fields: {sorted(bad)}")
    return v


class _Validated(BaseModel):
    @field_validator("schedule_cron", check_fields=False)
    @classmethod
    def _cron(cls, v: str | None) -> str | None:
        return check_cron(v)

    @field_validator("album_template", check_fields=False)
    @classmethod
    def _tmpl(cls, v: str | None) -> str | None:
        return check_template(v)

    @field_validator("gdl_options", check_fields=False)
    @classmethod
    def _gdl(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return check_gdl_options(v)


def check_gdl_options(v: dict[str, Any] | None) -> dict[str, Any] | None:
    return v if v is None else validate_gdl_options(v)


class SourceIn(_Validated):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    target_id: int
    credential_id: int | None = None
    album_template: str = ""
    schedule_cron: str | None = None
    backfill_mode: BackfillMode = BackfillMode.full
    backfill_value: str | None = None
    allow_animated: bool = False
    filters: dict[str, Any] = {}
    notify: dict[str, Any] = {}
    gdl_options: dict[str, Any] = {}
    proxy: str | None = None
    log_level: str | None = None
    enabled: bool = True
    ephemeral: bool = False
    visibility: Visibility = Visibility.private


class SourcePatch(_Validated):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    target_id: int | None = None
    credential_id: int | None = None
    album_template: str | None = None
    schedule_cron: str | None = None
    backfill_mode: BackfillMode | None = None
    backfill_value: str | None = None
    allow_animated: bool | None = None
    filters: dict[str, Any] | None = None
    notify: dict[str, Any] | None = None
    gdl_options: dict[str, Any] | None = None
    proxy: str | None = None
    log_level: str | None = None
    enabled: bool | None = None
    ephemeral: bool | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    extractor: str
    target_id: int
    credential_id: int | None
    album_template: str
    schedule_cron: str | None
    backfill_mode: BackfillMode
    backfill_value: str | None
    allow_animated: bool
    filters: dict[str, Any]
    notify: dict[str, Any]
    gdl_options: dict[str, Any]
    proxy: str | None
    log_level: str | None
    enabled: bool
    ephemeral: bool
    owner_id: int
    visibility: Visibility

    @classmethod
    def of(cls, s: Source) -> "SourceOut":
        return cls.model_validate(s)
