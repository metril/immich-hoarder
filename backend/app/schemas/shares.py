from pydantic import BaseModel

from app.db.models import Perm, PrincipalType, Visibility


class ShareEntry(BaseModel):
    principal_type: PrincipalType
    principal_id: str
    perm: Perm


class SharesBody(BaseModel):
    visibility: Visibility
    shares: list[ShareEntry]
