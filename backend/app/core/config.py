import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secrets import load_or_create

MIN_SECRET_LENGTH = 32
_ENV_PREFIX = "IH_"
_FILE_SECRETS = ("database_url", "master_key", "session_secret")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IH_", extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(
        default="sqlite+aiosqlite:////data/hoarder.db",
        repr=False,
        description="SQLAlchemy async database URL (SQLite or PostgreSQL); may embed a password.",
    )
    master_key: SecretStr | None = Field(
        default=None,
        description=(
            "Override for the key that encrypts stored credentials (at least 32 characters); "
            "unset uses an auto-generated key in the data directory."
        ),
    )
    data_dir: Path = Field(
        default=Path("/data"),
        description="Directory for persistent data; auto-generated secrets live in its secrets/.",
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
    log_level: Literal["error", "warn", "info", "debug", "trace"] = Field(
        default="info", description="Minimum severity of emitted log lines."
    )
    session_secret: SecretStr | None = Field(
        default=None,
        description=(
            "Override for the secret that signs session cookies (at least 32 characters); "
            "unset uses an auto-generated secret in the data directory."
        ),
    )
    break_glass: bool = Field(
        default=False,
        description=(
            "Force local-account login on regardless of the UI setting, and allow "
            "creating the local admin when none exists. Unset after recovery."
        ),
    )
    break_glass_reset: bool = Field(
        default=False,
        description="With break glass: allow resetting an existing local admin's password.",
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
    def _min_secret_length(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and len(v.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f"must be at least {MIN_SECRET_LENGTH} characters")
        return v

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    def master_key_value(self) -> str:
        """Configured master key, else the auto-generated one (created on first use)."""
        if self.master_key is not None:
            return self.master_key.get_secret_value()
        return load_or_create("master_key", self.secrets_dir)

    def session_secret_value(self) -> str:
        if self.session_secret is not None:
            return self.session_secret.get_secret_value()
        return load_or_create("session_secret", self.secrets_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
