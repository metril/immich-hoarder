from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Job, JobEvent, JobItem, JobStatus
from app.schemas import UtcDatetime
from app.schemas.sources import SourceIn

LOG_LEVELS = ("trace", "debug", "info", "warn", "error")


_LEVEL = "Log level for this run: trace, debug, info, warn or error."


class RunIn(BaseModel):
    log_level: str | None = Field(
        default=None,
        pattern="^(trace|debug|info|warn|error)$",
        description=_LEVEL,
        examples=["info"],
    )


class RipIn(SourceIn):
    """Ad-hoc rip: a source-create payload (name optional, schedule ignored)."""

    name: str = Field(
        default="", max_length=255, description="Optional display name.", examples=["one-off"]
    )
    log_level: str | None = Field(
        default=None,
        pattern="^(trace|debug|info|warn|error)$",
        description=_LEVEL,
        examples=["info"],
    )


class JobOut(BaseModel):
    id: int = Field(description="Job id.", examples=[17])
    source_id: int = Field(description="Id of the source the job runs.", examples=[3])
    source_name: str | None = Field(description="Name of the source.", examples=["Artist feed"])
    status: JobStatus = Field(description="Lifecycle state of the job.", examples=["running"])
    log_level: str | None = Field(description="Log level the job runs with.", examples=["info"])
    phase: str | None = Field(
        description="Current phase while running (e.g. fetching, uploading).",
        examples=["uploading"],
    )
    counters: dict[str, Any] = Field(
        description="Progress counters, e.g. seen, uploaded, skipped, failed.",
        examples=[{"seen": 40, "uploaded": 12, "skipped": 28, "failed": 0}],
    )
    error: str | None = Field(description="Failure message when the job failed.", examples=[None])
    triggered_by: int | None = Field(
        description="Id of the user who started it; null for scheduled runs.", examples=[1]
    )
    created_at: UtcDatetime = Field(
        description="When the job was queued.", examples=["2026-01-01T03:00:00Z"]
    )
    started_at: UtcDatetime | None = Field(
        description="When it started running.", examples=["2026-01-01T03:00:01Z"]
    )
    finished_at: UtcDatetime | None = Field(
        description="When it reached a terminal state.", examples=["2026-01-01T03:05:00Z"]
    )

    @classmethod
    def of(cls, j: Job, source_name: str | None) -> "JobOut":
        return cls(
            id=j.id,
            source_id=j.source_id,
            source_name=source_name,
            status=j.status,
            log_level=j.log_level,
            phase=j.phase,
            counters=j.counters or {},
            error=j.error,
            triggered_by=j.triggered_by,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
        )


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="Item id.", examples=[101])
    url: str = Field(
        description="Source URL of the media item.", examples=["https://example.com/a.jpg"]
    )
    outcome: str = Field(
        description="Result for the item: uploaded, skipped, failed or similar.",
        examples=["uploaded"],
    )
    reason: str | None = Field(description="Why it was skipped or failed.", examples=["duplicate"])
    immich_asset_id: str | None = Field(
        description="Immich asset id once uploaded.",
        examples=["0b7c1d1e-9a40-4d6f-8d5e-2a1f3c4b5d6e"],
    )

    @classmethod
    def of(cls, i: JobItem) -> "ItemOut":
        return cls.model_validate(i)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="Event id.", examples=[900])
    ts: UtcDatetime = Field(
        description="When the event happened.", examples=["2026-01-01T03:00:05Z"]
    )
    level: str = Field(
        description="Severity: trace, debug, info, warn or error.", examples=["info"]
    )
    type: str = Field(description="Event kind, e.g. log, phase, item.", examples=["log"])
    data: dict[str, Any] = Field(
        description="Event payload; shape depends on `type`.",
        examples=[{"msg": "fetched 40 items"}],
    )

    @classmethod
    def of(cls, e: JobEvent) -> "EventOut":
        return cls.model_validate(e)
