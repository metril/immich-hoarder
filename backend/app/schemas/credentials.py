from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.extractors import normalize_site
from app.db.models import Credential, CredentialKind, Visibility


class CredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    site: str = Field(min_length=1, max_length=255)
    kind: CredentialKind
    secret: str = Field(min_length=1)  # write-only
    visibility: Visibility = Visibility.private

    @field_validator("site")
    @classmethod
    def _site(cls, v: str) -> str:
        return normalize_site(v)


class CredentialPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    site: str | None = Field(default=None, min_length=1, max_length=255)
    kind: CredentialKind | None = None
    secret: str | None = Field(default=None, min_length=1)

    @field_validator("site")
    @classmethod
    def _site(cls, v: str | None) -> str | None:
        return None if v is None else normalize_site(v)


class CredentialOut(BaseModel):
    id: int
    name: str
    site: str
    kind: CredentialKind
    owner_id: int
    visibility: Visibility
    has_secret: bool
    can_edit: bool  # output-only: caller may PATCH
    can_use: bool  # output-only: caller may reference it from a source

    @classmethod
    def of(cls, c: Credential, can_edit: bool, can_use: bool) -> "CredentialOut":
        return cls(
            id=c.id,
            name=c.name,
            site=c.site,
            kind=c.kind,
            owner_id=c.owner_id,
            visibility=c.visibility,
            has_secret=bool(c.secret_enc),
            can_edit=can_edit,
            can_use=can_use,
        )
