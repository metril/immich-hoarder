from datetime import datetime

from pydantic import BaseModel, Field

from app.auth.principal import Scope
from app.schemas import UtcDatetime


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[Scope]
    expires_at: datetime | None = None


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
    id: int
    name: str
    prefix: str
    scopes: list[str]
    expires_at: UtcDatetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str
