import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IH_", extra="ignore")

    database_url: str = "sqlite+aiosqlite:////data/hoarder.db"
    master_key: SecretStr
    scratch_dir: Path = Path("/scratch")
    scratch_max_bytes: int = 4 * 1024**3
    max_concurrent_jobs: int = os.cpu_count() or 1
    log_level: Literal["error", "warn", "info", "debug", "trace"] = "info"
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_admin_groups: list[str] = ["hoarder-admins"]
    oidc_user_groups: list[str] = ["hoarder-users"]
    public_url: str
    session_secret: SecretStr
    trusted_proxies: list[str] = []

    @field_validator("master_key", "session_secret")
    @classmethod
    def _min_secret_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f"must be at least {MIN_SECRET_LENGTH} characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
