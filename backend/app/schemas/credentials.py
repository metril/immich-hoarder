from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.extractors import normalize_site
from app.db.models import Credential, CredentialKind, Visibility

_NAME = "Display name."
_SITE = "Site (extractor category) the credential is for; normalised to lower case."
_KIND = "How the secret is used: oauth, cookies, userpass, token or apprise (notification URL)."
_SECRET = "Secret material (write-only; never returned)."


class CredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=255, description=_NAME, examples=["Pixiv login"])
    site: str = Field(min_length=1, max_length=255, description=_SITE, examples=["pixiv"])
    kind: CredentialKind = Field(description=_KIND, examples=["token"])
    secret: str = Field(min_length=1, description=_SECRET, examples=["secret-value"])
    visibility: Visibility = Field(
        default=Visibility.private, description="Who can see and use it.", examples=["private"]
    )

    @field_validator("site")
    @classmethod
    def _site(cls, v: str) -> str:
        return normalize_site(v)


class CredentialPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(
        default=None, min_length=1, max_length=255, description=_NAME, examples=["Pixiv login"]
    )
    site: str | None = Field(
        default=None, min_length=1, max_length=255, description=_SITE, examples=["pixiv"]
    )
    kind: CredentialKind | None = Field(default=None, description=_KIND, examples=["token"])
    secret: str | None = Field(
        default=None, min_length=1, description=_SECRET, examples=["secret-value"]
    )

    @field_validator("site")
    @classmethod
    def _site(cls, v: str | None) -> str | None:
        return None if v is None else normalize_site(v)


class CredentialOut(BaseModel):
    id: int = Field(description="Credential id.", examples=[1])
    name: str = Field(description=_NAME, examples=["Pixiv login"])
    site: str = Field(description=_SITE, examples=["pixiv"])
    kind: CredentialKind = Field(description=_KIND, examples=["token"])
    owner_id: int = Field(description="Id of the owning user.", examples=[1])
    visibility: Visibility = Field(description="Who can see and use it.", examples=["private"])
    has_secret: bool = Field(description="Whether a secret is stored.", examples=[True])
    can_edit: bool = Field(description="Output-only: the caller may PATCH it.", examples=[True])
    can_use: bool = Field(
        description="Output-only: the caller may reference it from a source.", examples=[True]
    )

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
