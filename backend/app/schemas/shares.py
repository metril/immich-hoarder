from pydantic import BaseModel, Field

from app.db.models import Perm, PrincipalType, Visibility


class ShareEntry(BaseModel):
    principal_type: PrincipalType = Field(
        description="Whether the grant is for a user or a group.", examples=["user"]
    )
    principal_id: str = Field(description="User id (as a string) or group name.", examples=["2"])
    perm: Perm = Field(
        description="`use` allows referencing/running; `edit` also allows changing.",
        examples=["use"],
    )
    principal_name: str | None = Field(
        default=None,
        description="Output-only display name (user name, or the group name); ignored on input.",
        examples=["Bob"],
    )


class SharesBody(BaseModel):
    visibility: Visibility = Field(
        description="Who can see it: `private`, `everyone` or `restricted` (to `shares`).",
        examples=["restricted"],
    )
    shares: list[ShareEntry] = Field(
        description="Explicit grants; only used when visibility is `restricted`."
    )
