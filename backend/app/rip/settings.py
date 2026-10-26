"""Admin-configurable rip settings (settings key "rip")."""

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.extractors import UnsupportedURL, validate_proxy
from app.runtime.settings import _load_model


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

    @field_validator("proxy")
    @classmethod
    def _check_proxy(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return validate_proxy(v, allow_private=True)
        except UnsupportedURL as e:
            raise ValueError(str(e)) from None


async def load_rip_settings(session: AsyncSession) -> RipSettings:
    return await _load_model(session, "rip", RipSettings)
