"""Admin-configurable rip settings (settings key "rip")."""

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.extractors import UnsupportedURL, validate_proxy
from app.runtime.settings import load_model

DEFAULT_SCRATCH_MAX_BYTES = 4 * 1024**3


class RateLimit(BaseModel, extra="forbid"):
    sleep_request: float = Field(
        default=1.0, ge=0, description="Seconds to wait between requests to the site."
    )
    sleep: float = Field(default=0.0, ge=0, description="Seconds to wait between file downloads.")
    retries: int = Field(default=4, ge=0, description="Number of retries after a failed request.")


class RipSettings(BaseModel, extra="forbid"):
    proxy: str | None = Field(
        default=None, description="Proxy URL used for all downloads; unset means no proxy."
    )
    rate_limits: dict[str, RateLimit] = Field(
        default={}, description="Per-site rate limits keyed by extractor name."
    )
    upload_concurrency: int = Field(
        default=4, ge=1, le=16, description="Number of simultaneous uploads to Immich."
    )
    job_scratch_max_bytes: int | None = Field(
        default=None,
        ge=1,
        description="Scratch size limit for a single job, in bytes; unset uses 4 GiB.",
    )
    allow_private_hosts: bool = Field(
        default=False, description="Allow downloads from private and loopback network addresses."
    )

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
    return await load_model(session, "rip", RipSettings)
