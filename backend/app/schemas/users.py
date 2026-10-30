from pydantic import BaseModel, ConfigDict, Field

from app.auth.local import MIN_PASSWORD_LENGTH
from app.db.models import Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="User id.", examples=[1])
    sub: str = Field(
        description="Stable subject: the OIDC `sub`, or `local:<username>` for local accounts.",
        examples=["local:alice"],
    )
    email: str | None = Field(
        description="Email address, when known.", examples=["alice@example.com"]
    )
    name: str | None = Field(description="Display name, when known.", examples=["Alice"])
    role: Role = Field(description="The user's role.", examples=["user"])
    groups: list[str] = Field(
        description="Group names from the identity provider.", examples=[["hoarder-users"]]
    )
    disabled: bool = Field(
        description="Disabled users cannot sign in or use API keys.", examples=[False]
    )


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool | None = Field(
        default=None,
        description="Disable or re-enable the user; omitted keeps the current state.",
        examples=[True],
    )


class UserRef(BaseModel):
    id: int = Field(description="User id.", examples=[2])
    name: str | None = Field(description="Display name.", examples=["Bob"])


class LocalUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(
        min_length=1,
        max_length=64,
        description="Login name; the account's sub becomes `local:<username>`.",
        examples=["alice"],
    )
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=1024,
        description=f"Initial password (at least {MIN_PASSWORD_LENGTH} characters).",
        examples=["correct horse battery"],
    )
    role: Role = Field(default=Role.user, description="Role of the new account.", examples=["user"])
    must_change_password: bool = Field(
        default=False,
        description="Prompt the user to choose a new password at first sign-in.",
        examples=[False],
    )


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=1024,
        description=f"New password (at least {MIN_PASSWORD_LENGTH} characters).",
        examples=["a new long password"],
    )
    must_change_password: bool = Field(
        default=True,
        description="Require the user to change this password at next sign-in.",
        examples=[True],
    )


class OwnedCounts(BaseModel):
    targets: int = Field(description="Immich targets owned by the user.", examples=[1])
    credentials: int = Field(description="Credentials owned by the user.", examples=[2])
    sources: int = Field(description="Sources owned by the user.", examples=[3])


class UserInUse(BaseModel):
    detail: str = Field(description="Why the delete was refused.", examples=["user owns resources"])
    owned: OwnedCounts = Field(description="Resources that would need reassigning.")
