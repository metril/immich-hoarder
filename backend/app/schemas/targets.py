from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ImmichTarget, Visibility


class TargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1)
    visibility: Visibility = Visibility.private


class TargetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    api_key: str | None = Field(default=None, min_length=1)


class TargetOut(BaseModel):
    id: int
    name: str
    url: str
    owner_id: int
    visibility: Visibility
    has_api_key: bool

    @classmethod
    def of(cls, t: ImmichTarget) -> "TargetOut":
        return cls(
            id=t.id,
            name=t.name,
            url=t.url,
            owner_id=t.owner_id,
            visibility=t.visibility,
            has_api_key=bool(t.api_key_enc),
        )
