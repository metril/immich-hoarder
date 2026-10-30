from pydantic import BaseModel, Field

from app.auth.local import MIN_PASSWORD_LENGTH
from app.db.models import Role


class MeOut(BaseModel):
    id: int = Field(description="User id.", examples=[1])
    email: str | None = Field(
        description="Email address, when known.", examples=["alice@example.com"]
    )
    name: str | None = Field(description="Display name, when known.", examples=["Alice"])
    role: Role = Field(description="The user's role.", examples=["admin"])
    groups: list[str] = Field(
        description="Group names from the identity provider.", examples=[["hoarder-admins"]]
    )
    must_change_password: bool = Field(
        default=False,
        description="True when this local account must choose a new password.",
        examples=[False],
    )


class AuthStatus(BaseModel):
    setup_required: bool = Field(
        description="True until the first admin account exists.", examples=[False]
    )
    oidc_enabled: bool = Field(
        description="OIDC sign-in is configured and enabled.", examples=[True]
    )
    local_login_enabled: bool = Field(
        description="Local username/password sign-in is allowed.", examples=[True]
    )
    break_glass: bool = Field(
        description="Break-glass mode forces local login on.", examples=[False]
    )
    reset_token_required: bool = Field(
        description="The setup call must carry the one-time reset token from the server log.",
        examples=[False],
    )


class LocalCredentials(BaseModel):
    username: str = Field(
        min_length=1, max_length=64, description="Local login name.", examples=["admin"]
    )
    password: str = Field(
        min_length=1,
        max_length=1024,
        description="Account password.",
        examples=["correct horse battery"],
    )


class SetupIn(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=64,
        description="Login name of the first admin.",
        examples=["admin"],
    )
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=1024,
        description=f"Password (at least {MIN_PASSWORD_LENGTH} characters).",
        examples=["correct horse battery"],
    )
    reset_token: str | None = Field(
        default=None,
        max_length=256,
        description="One-time token from the server log; only needed in break-glass reset mode.",
        examples=[None],
    )


class LocalPasswordIn(BaseModel):
    current_password: str | None = Field(
        default=None,
        max_length=1024,
        description="Current local admin password; required when one already exists.",
        examples=["old password"],
    )
    new_password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=1024,
        description=f"New password (at least {MIN_PASSWORD_LENGTH} characters).",
        examples=["a new long password"],
    )
    username: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Rename the local admin; omitted keeps the current name.",
        examples=["admin"],
    )


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
    issuer: str | None = Field(
        default=None,
        description="Issuer URL to test; omitted tests the saved configuration.",
        examples=["https://auth.example.com/application/o/hoarder/"],
    )


class OidcTestOut(BaseModel):
    ok: bool = Field(description="True when discovery succeeded.", examples=[True])
    error: str | None = Field(default=None, description="Why discovery failed.", examples=[None])
