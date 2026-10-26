from pydantic import BaseModel, ConfigDict

from app.db.models import Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sub: str
    email: str | None
    name: str | None
    role: Role
    groups: list[str]
    disabled: bool


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool | None = None


class UserRef(BaseModel):
    id: int
    name: str | None
    email: str | None
