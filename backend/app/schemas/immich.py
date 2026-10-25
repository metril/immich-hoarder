from pydantic import BaseModel


class TargetTestOut(BaseModel):
    ok: bool
    version: str | None = None
    missing_permissions: list[str] = []
    error: str | None = None


class AlbumOut(BaseModel):
    id: str
    name: str
    asset_count: int


class AlbumList(BaseModel):
    items: list[AlbumOut]
