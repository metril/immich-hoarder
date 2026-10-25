"""Admin-configurable rip settings (settings key "rip")."""

import logging

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting

log = logging.getLogger(__name__)


class RateLimit(BaseModel, extra="forbid"):
    sleep_request: float = Field(default=1.0, ge=0)
    sleep: float = Field(default=0.0, ge=0)
    retries: int = Field(default=4, ge=0)


class RipSettings(BaseModel, extra="forbid"):
    proxy: str | None = None
    rate_limits: dict[str, RateLimit] = {}
    upload_concurrency: int = Field(default=4, ge=1, le=16)
    job_scratch_max_bytes: int | None = Field(default=None, ge=1)
    allow_private_hosts: bool = False


async def load_rip_settings(session: AsyncSession) -> RipSettings:
    row = await session.get(Setting, "rip")
    if row is None:
        return RipSettings()
    try:
        return RipSettings.model_validate(row.value)
    except ValidationError:
        log.warning("invalid rip settings stored; using defaults")
        return RipSettings()
