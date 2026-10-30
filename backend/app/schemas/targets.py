from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ImmichTarget, Visibility

_NAME = "Display name."
_URL = "Base URL of the Immich server."
_KEY = "Immich API key (write-only; never returned)."
_EX_URL = "https://immich.example.com"


class TargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=255, description=_NAME, examples=["Home Immich"])
    url: str = Field(min_length=1, max_length=2048, description=_URL, examples=[_EX_URL])
    api_key: str = Field(min_length=1, description=_KEY, examples=["immich-api-key"])
    visibility: Visibility = Field(
        default=Visibility.private,
        description="Who can see and use the target.",
        examples=["private"],
    )


class TargetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(
        default=None, min_length=1, max_length=255, description=_NAME, examples=["Home Immich"]
    )
    url: str | None = Field(
        default=None, min_length=1, max_length=2048, description=_URL, examples=[_EX_URL]
    )
    api_key: str | None = Field(
        default=None, min_length=1, description=_KEY, examples=["immich-api-key"]
    )


class TargetOut(BaseModel):
    id: int = Field(description="Target id.", examples=[1])
    name: str = Field(description=_NAME, examples=["Home Immich"])
    url: str = Field(description=_URL, examples=[_EX_URL])
    owner_id: int = Field(description="Id of the owning user.", examples=[1])
    visibility: Visibility = Field(
        description="Who can see and use the target.", examples=["private"]
    )
    has_api_key: bool = Field(description="Whether an API key is stored.", examples=[True])
    can_edit: bool = Field(description="Output-only: the caller may PATCH it.", examples=[True])
    can_use: bool = Field(
        description="Output-only: the caller may reference it from a source.", examples=[True]
    )

    @classmethod
    def of(cls, t: ImmichTarget, can_edit: bool, can_use: bool) -> "TargetOut":
        return cls(
            id=t.id,
            name=t.name,
            url=t.url,
            owner_id=t.owner_id,
            visibility=t.visibility,
            has_api_key=bool(t.api_key_enc),
            can_edit=can_edit,
            can_use=can_use,
        )
