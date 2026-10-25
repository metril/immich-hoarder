from app.auth.apikeys import create_api_key
from app.auth.principal import SCOPES
from app.db.engine import session_scope
from app.db.models import Role, User

USER_SCOPES = sorted(SCOPES - {"admin"})


async def make_user(sub: str, role: Role = Role.user) -> int:
    async with session_scope() as s:
        u = User(
            sub=sub, role=role, groups=["hoarder-admins" if role == Role.admin else "hoarder-users"]
        )
        s.add(u)
        await s.flush()
        return u.id


async def headers_for(uid: int, scopes: list[str] | None = None) -> dict[str, str]:
    async with session_scope() as s:
        user = await s.get(User, uid)
        assert user
        sc = (
            scopes
            if scopes is not None
            else USER_SCOPES + (["admin"] if user.role == Role.admin else [])
        )
        _, raw = await create_api_key(s, user, "t", sc, None)
    return {"X-API-Key": raw}


async def actor(sub: str, role: Role = Role.user) -> tuple[int, dict[str, str]]:
    uid = await make_user(sub, role)
    return uid, await headers_for(uid)


TARGET = {"name": "t", "url": "http://immich", "api_key": "k-secret"}
