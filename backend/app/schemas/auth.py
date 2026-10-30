from pydantic import BaseModel, Field

from app.auth.local import MIN_PASSWORD_LENGTH
from app.db.models import Role


class MeOut(BaseModel):
    id: int
    email: str | None
    name: str | None
    role: Role
    groups: list[str]
    must_change_password: bool = Field(
        default=False,
        description="True when this local account must choose a new password.",
        examples=[False],
    )


class AuthStatus(BaseModel):
    setup_required: bool
    oidc_enabled: bool
    local_login_enabled: bool
    break_glass: bool
    reset_token_required: bool


class LocalCredentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class SetupIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)
    reset_token: str | None = Field(default=None, max_length=256)


class LocalPasswordIn(BaseModel):
    current_password: str | None = Field(default=None, max_length=1024)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)
    username: str | None = Field(default=None, min_length=1, max_length=64)


class SelfPasswordIn(BaseModel):
    current_password: str = Field(
        max_length=1024, description="Your current password.", examples=["old password"]
    )
    new_password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=1024,
        description=f"New password (at least {MIN_PASSWORD_LENGTH} characters).",
        examples=["a new long password"],
    )


class OidcTestIn(BaseModel):
    issuer: str | None = None


class OidcTestOut(BaseModel):
    ok: bool
    error: str | None = None
