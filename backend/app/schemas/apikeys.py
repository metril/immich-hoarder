from datetime import datetime

from pydantic import BaseModel, Field

from app.auth.principal import Scope
from app.schemas import UtcDatetime


class ApiKeyIn(BaseModel):
    name: str = Field(
        min_length=1, max_length=255, description="Display name.", examples=["ci-pipeline"]
    )
    scopes: list[Scope] = Field(
        description="Scopes granted to the key; may not exceed the caller's own.",
        examples=[["jobs:read", "sources:run"]],
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Expiry time (ISO 8601); omitted means the key never expires.",
        examples=["2027-01-01T00:00:00Z"],
    )


class ApiKeyPatch(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New display name; omitted keeps the current name.",
        examples=["ci-pipeline"],
    )
    scopes: list[Scope] | None = Field(
        default=None,
        description="Replacement scope list; omitted keeps the current scopes.",
        examples=[["jobs:read", "sources:read"]],
    )


class ApiKeyOut(BaseModel):
    id: int = Field(description="Key id.", examples=[1])
    name: str = Field(description="Display name.", examples=["ci-pipeline"])
    prefix: str = Field(
        description="Leading characters of the key, to recognise it by.", examples=["ih_a1b2c3d4"]
    )
    scopes: list[str] = Field(description="Granted scopes.", examples=[["jobs:read"]])
    expires_at: UtcDatetime | None = Field(
        description="Expiry time, or null when it never expires.", examples=["2027-01-01T00:00:00Z"]
    )


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(
        description="The full secret key. Shown only once; store it now.",
        examples=["ih_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"],
    )
