from pydantic import BaseModel, Field


class TargetTestOut(BaseModel):
    ok: bool = Field(
        description="True when the target is reachable and the key is usable.", examples=[True]
    )
    version: str | None = Field(
        default=None, description="Immich server version.", examples=["1.130.0"]
    )
    missing_permissions: list[str] = Field(
        default=[], description="Required Immich API-key permissions the key lacks.", examples=[[]]
    )
    optional_missing: list[str] = Field(
        default=[],
        description="Optional permissions the key lacks (reduced features).",
        examples=[[]],
    )
    error: str | None = Field(default=None, description="Why the check failed.", examples=[None])


class AlbumOut(BaseModel):
    id: str = Field(
        description="Immich album id (UUID).", examples=["0b7c1d1e-9a40-4d6f-8d5e-2a1f3c4b5d6e"]
    )
    name: str = Field(description="Album name.", examples=["Holiday"])
    asset_count: int = Field(description="Number of assets in the album.", examples=[42])


class AlbumList(BaseModel):
    items: list[AlbumOut] = Field(description="Albums on the target.")
