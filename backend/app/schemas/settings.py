from pydantic import BaseModel, ConfigDict

from app.auth.settings import AuthSettings, OidcSettings
from app.rip.settings import RipSettings
from app.runtime.settings import NotifySettings, RuntimeSettings


class SettingsDoc(BaseModel):
    """Admin settings document; each key is optional and replaced as a whole when present."""

    model_config = ConfigDict(extra="forbid")
    rip: RipSettings | None = None
    runtime: RuntimeSettings | None = None
    notify: NotifySettings | None = None
    oidc: OidcSettings | None = None
    auth: AuthSettings | None = None
