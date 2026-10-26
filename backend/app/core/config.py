import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32
_ENV_PREFIX = "IH_"
_FILE_SECRETS = ("master_key", "session_secret", "oidc_client_secret")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IH_", extra="ignore", hide_input_in_errors=True)

    database_url: str = "sqlite+aiosqlite:////data/hoarder.db"
    master_key: SecretStr
    scratch_dir: Path = Path("/scratch")
    backup_dir: Path = Path("/data/backups")
    scratch_max_bytes: int = 4 * 1024**3
    max_concurrent_jobs: int = os.cpu_count() or 1
    log_level: Literal["error", "warn", "info", "debug", "trace"] = "info"
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_admin_groups: list[str] = ["hoarder-admins"]
    oidc_user_groups: list[str] = ["hoarder-users"]
    oidc_groups_claim: str = "groups"
    public_url: str
    session_secret: SecretStr

    @model_validator(mode="before")
    @classmethod
    def _load_secret_files(cls, data: Any) -> Any:
        """Docker-secrets style: IH_<NAME>_FILE is read when IH_<NAME> is unset."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for name in _FILE_SECRETS:
            var = f"{_ENV_PREFIX}{name.upper()}"
            path = os.environ.get(f"{var}_FILE")
            if path and name not in data and var not in os.environ:
                text = Path(path).read_text()
                data[name] = text.removesuffix("\n")
        return data

    @field_validator("master_key", "session_secret")
    @classmethod
    def _min_secret_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f"must be at least {MIN_SECRET_LENGTH} characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
