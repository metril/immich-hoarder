from pydantic import BaseModel, ConfigDict, Field

from app.auth.settings import AuthSettings, OidcSettings
from app.rip.settings import RipSettings
from app.runtime.settings import NotifySettings, RuntimeSettings


class SettingsDoc(BaseModel):
    """Admin settings document; each key is optional and replaced as a whole when present."""

    model_config = ConfigDict(extra="forbid")
    rip: RipSettings | None = Field(
        default=None, description="Ripping defaults (gallery-dl options, limits, scratch)."
    )
    runtime: RuntimeSettings | None = Field(
        default=None, description="Job runtime: concurrency, timeouts and retention."
    )
    notify: NotifySettings | None = Field(default=None, description="Notification defaults.")
    oidc: OidcSettings | None = Field(
        default=None, description="OIDC provider configuration (the client secret is write-only)."
    )
    auth: AuthSettings | None = Field(
        default=None, description="Which sign-in methods are enabled."
    )
