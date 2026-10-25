from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Credential, CredentialKind, Visibility


class CredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    site: str = Field(min_length=1, max_length=255)
    kind: CredentialKind
    secret: str = Field(min_length=1)  # write-only
    visibility: Visibility = Visibility.private


class CredentialPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    site: str | None = Field(default=None, min_length=1, max_length=255)
    kind: CredentialKind | None = None
    secret: str | None = Field(default=None, min_length=1)


class CredentialOut(BaseModel):
    id: int
    name: str
    site: str
    kind: CredentialKind
    owner_id: int
    visibility: Visibility
    has_secret: bool

    @classmethod
    def of(cls, c: Credential) -> "CredentialOut":
        return cls(
            id=c.id,
            name=c.name,
            site=c.site,
            kind=c.kind,
            owner_id=c.owner_id,
            visibility=c.visibility,
            has_secret=bool(c.secret_enc),
        )
