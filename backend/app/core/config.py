import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32
_ENV_PREFIX = "IH_"
_FILE_SECRETS = ("database_url", "master_key", "session_secret", "oidc_client_secret")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IH_", extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(
        default="sqlite+aiosqlite:////data/hoarder.db",
        repr=False,
        description="SQLAlchemy async database URL (SQLite or PostgreSQL); may embed a password.",
    )
    master_key: SecretStr = Field(
        description="Key that encrypts stored credentials; at least 32 characters.",
    )
    scratch_dir: Path = Field(
        default=Path("/scratch"), description="Directory for temporary download files."
    )
    backup_dir: Path = Field(
        default=Path("/data/backups"), description="Directory where database backups are written."
    )
    web_dir: Path = Field(
        default=Path("/srv/web"), description="Directory containing the built web UI."
    )
    scratch_max_bytes: int = Field(
        default=4 * 1024**3,
        description="Total size limit of the scratch directory, in bytes.",
    )
    max_concurrent_jobs: int = Field(
        default=os.cpu_count() or 1,
        description="Maximum number of jobs run at the same time; defaults to the CPU count.",
    )
    log_level: Literal["error", "warn", "info", "debug", "trace"] = Field(
        default="info", description="Minimum severity of emitted log lines."
    )
    oidc_issuer: str | None = Field(
        default=None, description="OIDC issuer URL; OIDC login is enabled when set."
    )
    oidc_client_id: str | None = Field(default=None, description="OIDC client ID.")
    oidc_client_secret: SecretStr | None = Field(default=None, description="OIDC client secret.")
    oidc_admin_groups: list[str] = Field(
        default=["hoarder-admins"],
        description="OIDC groups granted the admin role, as a JSON list.",
    )
    oidc_user_groups: list[str] = Field(
        default=["hoarder-users"],
        description="OIDC groups granted the user role, as a JSON list.",
    )
    oidc_groups_claim: str = Field(
        default="groups", description="Name of the OIDC claim that lists the user's groups."
    )
    public_url: str = Field(
        description="Externally visible base URL of this service, used for OIDC redirects."
    )
    session_secret: SecretStr = Field(
        description="Secret that signs session cookies; at least 32 characters.",
    )

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
                try:
                    text = Path(path).read_text()
                except OSError as e:
                    raise ValueError(f"{var}_FILE: cannot read {path}: {e.strerror}") from None
                data[name] = text.rstrip("\r\n")
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
