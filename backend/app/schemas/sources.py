from string import Formatter
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from app.core.cronutil import validate_cron
from app.core.extractors import validate_gdl_options
from app.db.models import BackfillMode, Source, Visibility
from app.rip.albums import ALBUM_FIELDS
from app.rip.filters import FilterSpec, validate_backfill


def check_cron(v: str | None) -> str | None:
    return None if v is None else validate_cron(v)


def check_template(v: str | None) -> str | None:
    if v is None:
        return v
    try:
        parsed = [(f, spec, conv) for _, f, spec, conv in Formatter().parse(v) if f is not None]
    except ValueError as e:
        raise ValueError(f"invalid album template: {e}") from None
    if any(spec or conv for _, spec, conv in parsed):
        raise ValueError("album template does not support format specs or conversions")
    names = {f for f, _, _ in parsed}
    if bad := names - ALBUM_FIELDS:
        raise ValueError(f"unknown album template fields: {sorted(bad)}")
    return v


class SourceNotify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential_ids: list[int] = []
    on: list[Literal["success", "failure", "new_items"]] = ["failure"]


# Runtime stays dict[str, Any]; the schema is exact so generated client types are precise.
FiltersT = Annotated[
    dict[str, Any], WithJsonSchema(FilterSpec.model_json_schema(mode="serialization"))
]
NotifyT = Annotated[
    dict[str, Any], WithJsonSchema(SourceNotify.model_json_schema(mode="serialization"))
]


class _Validated(BaseModel):
    @field_validator("notify", check_fields=False)
    @classmethod
    def _notify(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        if not v:
            return {}
        return SourceNotify.model_validate(v).model_dump(mode="json")

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

    @field_validator("filters", check_fields=False)
    @classmethod
    def _filters(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        return FilterSpec.model_validate(v).model_dump(mode="json", exclude_none=False)


def check_gdl_options(v: dict[str, Any] | None) -> dict[str, Any] | None:
    return v if v is None else validate_gdl_options(v)


_D: dict[str, tuple[str, Any]] = {
    "id": ("Source id.", 1),
    "name": ("Display name.", "Artist feed"),
    "url": ("Gallery or profile URL to rip.", "https://www.pixiv.net/en/users/123"),
    "extractor": ("Extractor (site) detected from the URL.", "pixiv"),
    "target_id": ("Id of the Immich target to upload to.", 1),
    "credential_id": ("Id of the credential used to log in to the site, if any.", 2),
    "album_template": (
        "Immich album name template using `{field}` placeholders; empty means no album.",
        "{category} - {user}",
    ),
    "schedule_cron": ("Cron expression (5 fields) for scheduled runs; null disables.", "0 3 * * *"),
    "backfill_mode": ("How much history the first run fetches: full, last_n or since.", "full"),
    "backfill_value": ("Count for `last_n` or ISO date for `since`; unused for `full`.", "100"),
    "allow_animated": ("Also upload animated media (ugoira, GIFs).", False),
    "reupload_deleted": ("Re-upload items that were previously deleted from Immich.", False),
    "filters": ("Item filters (see the filter schema); empty keeps everything.", {}),
    "notify": ("Notification settings: credential ids and events to notify on.", {}),
    "gdl_options": ("Extra gallery-dl options (validated against an allowlist).", {}),
    "proxy": ("Proxy URL used for this source.", "socks5://proxy.example.com:1080"),
    "log_level": ("Log level for this source's jobs: trace, debug, info, warn or error.", "info"),
    "enabled": ("Disabled sources are skipped by the scheduler.", True),
    "ephemeral": ("Delete the source automatically after its first run.", False),
    "visibility": ("Who can see and use the source.", "private"),
    "owner_id": ("Id of the owning user.", 1),
    "can_edit": ("Output-only: the caller may PATCH it.", True),
    "can_use": ("Output-only: the caller may run it.", True),
}


def F(key: str, default: Any = ..., **kw: Any) -> Any:
    desc, ex = _D[key]
    return Field(default, description=desc, examples=[ex], **kw)


class SourceIn(_Validated):
    name: str = F("name", min_length=1, max_length=255)
    url: str = F("url", min_length=1, max_length=2048)
    target_id: int = F("target_id")
    credential_id: int | None = F("credential_id", None)
    album_template: str = F("album_template", "")
    schedule_cron: str | None = F("schedule_cron", None)
    backfill_mode: BackfillMode = F("backfill_mode", BackfillMode.full)
    backfill_value: str | None = F("backfill_value", None)
    allow_animated: bool = F("allow_animated", False)
    reupload_deleted: bool = F("reupload_deleted", False)
    filters: FiltersT = F("filters", {})
    notify: NotifyT = F("notify", {})
    gdl_options: dict[str, Any] = F("gdl_options", {})
    proxy: str | None = F("proxy", None)
    log_level: str | None = F("log_level", None)
    enabled: bool = F("enabled", True)
    ephemeral: bool = F("ephemeral", False)
    visibility: Visibility = F("visibility", Visibility.private)

    @model_validator(mode="after")
    def _backfill(self) -> "SourceIn":
        validate_backfill(self.backfill_mode, self.backfill_value)
        return self


class SourcePatch(_Validated):
    model_config = ConfigDict(extra="forbid")
    name: str | None = F("name", None, min_length=1, max_length=255)
    url: str | None = F("url", None, min_length=1, max_length=2048)
    target_id: int | None = F("target_id", None)
    credential_id: int | None = F("credential_id", None)
    album_template: str | None = F("album_template", None)
    schedule_cron: str | None = F("schedule_cron", None)
    backfill_mode: BackfillMode | None = F("backfill_mode", None)
    backfill_value: str | None = F("backfill_value", None)
    allow_animated: bool | None = F("allow_animated", None)
    reupload_deleted: bool | None = F("reupload_deleted", None)
    filters: FiltersT | None = F("filters", None)
    notify: NotifyT | None = F("notify", None)
    gdl_options: dict[str, Any] | None = F("gdl_options", None)
    proxy: str | None = F("proxy", None)
    log_level: str | None = F("log_level", None)
    enabled: bool | None = F("enabled", None)
    ephemeral: bool | None = F("ephemeral", None)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int = F("id")
    name: str = F("name")
    url: str = F("url")
    extractor: str = F("extractor")
    target_id: int = F("target_id")
    credential_id: int | None = F("credential_id")
    album_template: str = F("album_template")
    schedule_cron: str | None = F("schedule_cron")
    backfill_mode: BackfillMode = F("backfill_mode")
    backfill_value: str | None = F("backfill_value")
    allow_animated: bool = F("allow_animated")
    reupload_deleted: bool = F("reupload_deleted")
    filters: FiltersT = F("filters")
    notify: NotifyT = F("notify")
    gdl_options: dict[str, Any] = F("gdl_options")
    proxy: str | None = F("proxy")
    log_level: str | None = F("log_level")
    enabled: bool = F("enabled")
    ephemeral: bool = F("ephemeral")
    owner_id: int = F("owner_id")
    visibility: Visibility = F("visibility")
    can_edit: bool = F("can_edit")
    can_use: bool = F("can_use")

    @classmethod
    def of(cls, s: Source, can_edit: bool, can_use: bool) -> "SourceOut":
        data = {f: getattr(s, f) for f in cls.model_fields if f not in ("can_edit", "can_use")}
        return cls.model_validate(data | {"can_edit": can_edit, "can_use": can_use})
