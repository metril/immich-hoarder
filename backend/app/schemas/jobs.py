from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Job, JobEvent, JobItem, JobStatus
from app.schemas.sources import SourceIn

LOG_LEVELS = ("trace", "debug", "info", "warn", "error")


class RunIn(BaseModel):
    log_level: str | None = Field(default=None, pattern="^(trace|debug|info|warn|error)$")


class RipIn(SourceIn):
    """Ad-hoc rip: a source-create payload (name optional, schedule ignored)."""

    name: str = Field(default="", max_length=255)
    log_level: str | None = Field(default=None, pattern="^(trace|debug|info|warn|error)$")


class JobOut(BaseModel):
    id: int
    source_id: int
    source_name: str | None
    status: JobStatus
    log_level: str | None
    counters: dict[str, Any]
    error: str | None
    triggered_by: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, j: Job, source_name: str | None) -> "JobOut":
        return cls(
            id=j.id,
            source_id=j.source_id,
            source_name=source_name,
            status=j.status,
            log_level=j.log_level,
            counters=j.counters or {},
            error=j.error,
            triggered_by=j.triggered_by,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
        )


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str
    outcome: str
    reason: str | None
    immich_asset_id: str | None

    @classmethod
    def of(cls, i: JobItem) -> "ItemOut":
        return cls.model_validate(i)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    level: str
    type: str
    data: dict[str, Any]

    @classmethod
    def of(cls, e: JobEvent) -> "EventOut":
        return cls.model_validate(e)
