from pydantic import BaseModel

from app.db.models import Perm, PrincipalType, Visibility


class ShareEntry(BaseModel):
    principal_type: PrincipalType
    principal_id: str
    perm: Perm
    # Output-only: display name (user name, or the group name); ignored on input.
    principal_name: str | None = None


class SharesBody(BaseModel):
    visibility: Visibility
    shares: list[ShareEntry]
