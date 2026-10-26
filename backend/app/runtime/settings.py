"""Admin-configurable runtime and notify settings (keys "runtime", "notify")."""

import logging
import threading
from typing import Literal

import apprise
from croniter import croniter
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting

log = logging.getLogger(__name__)


async def load_model[M: BaseModel](session: AsyncSession, key: str, model: type[M]) -> M:
    """Load a settings row validated as ``model``; defaults if missing or invalid."""
    row = await session.get(Setting, key)
    if row is None:
        return model()
    try:
        return model.model_validate(row.value)
    except ValidationError:
        # Never log the validation detail: it may echo secret values.
        log.warning("invalid %s settings stored; using defaults", key)
        return model()


class RuntimeSettings(BaseModel, extra="forbid"):
    retention_days: int = Field(default=30, ge=1, le=3650)
    backup_cron: str = "0 3 * * *"
    backup_keep: int = Field(default=7, ge=0, le=365)
    max_concurrent_jobs: int | None = Field(default=None, ge=1, le=64)
    cancel_grace_s: int = Field(default=10, ge=0, le=300)

    @field_validator("backup_cron")
    @classmethod
    def _check_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError("invalid cron expression")
        return v


class _Quiet(logging.Filter):
    """Drop apprise records emitted by the thread currently validating a URL."""

    local = threading.local()

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(self.local, "active", False)


logging.getLogger("apprise").addFilter(_Quiet())


def _apprise_ok(url: str) -> bool:
    # apprise logs the offending URL on failure; keep it out of our logs.
    _Quiet.local.active = True
    try:
        return bool(apprise.Apprise().add(url))
    finally:
        _Quiet.local.active = False


class NotifySettings(BaseModel, extra="forbid"):
    urls: list[str] = []
    on: list[Literal["success", "failure", "new_items"]] = ["failure"]

    @field_validator("urls")
    @classmethod
    def _check_urls(cls, v: list[str]) -> list[str]:
        for i, url in enumerate(v):
            if not _apprise_ok(url):
                raise ValueError(f"invalid notification url at index {i}")
        return v


async def load_runtime_settings(session: AsyncSession) -> RuntimeSettings:
    return await load_model(session, "runtime", RuntimeSettings)


async def load_notify_settings(session: AsyncSession) -> NotifySettings:
    return await load_model(session, "notify", NotifySettings)
