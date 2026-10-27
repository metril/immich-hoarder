"""Admin-configurable auth settings (keys "oidc", "auth", "local_admin") and live reload."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import BearerVerifier, OidcConfig, build_oauth
from app.core.crypto import SecretBox, SecretDecryptError
from app.db.models import Setting
from app.runtime.settings import load_model

log = logging.getLogger(__name__)


class OidcSettings(BaseModel, extra="forbid"):
    """API shape of the OIDC settings; the client secret is write-only."""

    enabled: bool = Field(default=False, description="Whether OIDC login is offered.")
    issuer: str | None = Field(default=None, description="OIDC issuer URL.")
    client_id: str | None = Field(default=None, description="OIDC client ID.")
    client_secret: str | None = Field(
        default=None,
        description="OIDC client secret; write-only, blank or unset keeps the stored one.",
    )
    client_secret_set: bool = Field(
        default=False, description="Whether a client secret is stored (read-only)."
    )
    admin_groups: list[str] = Field(
        default=["hoarder-admins"], description="OIDC groups granted the admin role."
    )
    user_groups: list[str] = Field(
        default=["hoarder-users"], description="OIDC groups granted the user role."
    )
    groups_claim: str = Field(
        default="groups", description="Name of the claim that lists the user's groups."
    )

    @field_validator("issuer", "client_id", "client_secret")
    @classmethod
    def _blank_is_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None

    @field_validator("issuer")
    @classmethod
    def _issuer_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("must be an http(s) URL")
        return v


class OidcStored(BaseModel):
    """Stored shape: the secret is Fernet-encrypted."""

    enabled: bool = False
    issuer: str | None = None
    client_id: str | None = None
    client_secret_enc: str | None = None
    admin_groups: list[str] = ["hoarder-admins"]
    user_groups: list[str] = ["hoarder-users"]
    groups_claim: str = "groups"


class AuthSettings(BaseModel, extra="forbid"):
    public_url: str | None = Field(
        default=None,
        description="Externally visible base URL, used for OIDC redirects; unset derives it.",
    )
    local_enabled: bool = Field(default=True, description="Whether local-account login is on.")

    @field_validator("public_url")
    @classmethod
    def _public_url(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("must be an http(s) URL")
        return v


class LocalAdmin(BaseModel):
    username: str
    password_hash: str


def stored_to_api(st: OidcStored) -> OidcSettings:
    return OidcSettings(
        enabled=st.enabled,
        issuer=st.issuer,
        client_id=st.client_id,
        client_secret_set=bool(st.client_secret_enc),
        admin_groups=st.admin_groups,
        user_groups=st.user_groups,
        groups_claim=st.groups_claim,
    )


def merge_oidc(new: OidcSettings, old: OidcStored, box: SecretBox) -> OidcStored:
    """Apply a PUT body over the stored value; a blank secret keeps the stored one."""
    enc = old.client_secret_enc
    if new.client_secret:
        enc = box.encrypt(new.client_secret.encode()).decode()
    return OidcStored(
        enabled=new.enabled,
        issuer=new.issuer,
        client_id=new.client_id,
        client_secret_enc=enc,
        admin_groups=new.admin_groups,
        user_groups=new.user_groups,
        groups_claim=new.groups_claim,
    )


def to_config(st: OidcStored, box: SecretBox) -> OidcConfig:
    secret: str | None = None
    if st.client_secret_enc:
        try:
            secret = box.decrypt(st.client_secret_enc.encode()).decode()
        except SecretDecryptError:
            log.warning("stored OIDC client secret cannot be decrypted; OIDC disabled")
    return OidcConfig(
        enabled=st.enabled,
        issuer=st.issuer,
        client_id=st.client_id,
        client_secret=secret,
        admin_groups=tuple(st.admin_groups),
        user_groups=tuple(st.user_groups),
        groups_claim=st.groups_claim,
    )


async def reload_auth(app: FastAPI, session: AsyncSession) -> None:
    """(Re)build OIDC state from the database; takes effect without a restart."""
    box = SecretBox(app.state.settings.master_key_value())
    cfg = to_config(await load_model(session, "oidc", OidcStored), box)
    app.state.oidc_cfg = cfg
    app.state.auth_cfg = await load_model(session, "auth", AuthSettings)
    app.state.oauth = build_oauth(cfg)
    app.state.verifier = BearerVerifier(cfg)


async def import_legacy_env(session: AsyncSession, box: SecretBox) -> None:
    """One-time import of deprecated IH_OIDC_*/IH_PUBLIC_URL env into the database."""
    env = os.environ
    issuer, client_id = env.get("IH_OIDC_ISSUER"), env.get("IH_OIDC_CLIENT_ID")
    secret = env.get("IH_OIDC_CLIENT_SECRET")
    if not secret and (path := env.get("IH_OIDC_CLIENT_SECRET_FILE")):
        try:
            secret = Path(path).read_text().rstrip("\r\n")
        except OSError:
            secret = None
    public_url = env.get("IH_PUBLIC_URL")
    imported: list[str] = []
    if issuer and client_id and secret and await session.get(Setting, "oidc") is None:
        data: dict[str, Any] = OidcStored(
            enabled=True,
            issuer=issuer,
            client_id=client_id,
            client_secret_enc=box.encrypt(secret.encode()).decode(),
        ).model_dump()
        for key, var in (
            ("admin_groups", "IH_OIDC_ADMIN_GROUPS"),
            ("user_groups", "IH_OIDC_USER_GROUPS"),
        ):
            if raw := env.get(var):
                try:
                    data[key] = [str(g) for g in json.loads(raw)]
                except (ValueError, TypeError):
                    pass
        if claim := env.get("IH_OIDC_GROUPS_CLAIM"):
            data["groups_claim"] = claim
        session.add(Setting(key="oidc", value=data))
        imported.append("IH_OIDC_*")
    if public_url and await session.get(Setting, "auth") is None:
        try:
            session.add(Setting(key="auth", value=AuthSettings(public_url=public_url).model_dump()))
            imported.append("IH_PUBLIC_URL")
        except ValueError:
            pass
    if imported:
        await session.commit()
        log.warning(
            "imported deprecated env %s into the database; configure it in the web UI "
            "and remove it from the environment",
            ", ".join(imported),
        )
