from pydantic import BaseModel

from app.db.models import Role


class MeOut(BaseModel):
    id: int
    email: str | None
    name: str | None
    role: Role
    groups: list[str]
