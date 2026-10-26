import httpx
from test_apikeys import make_key, make_user


async def test_bearer_ih_token_is_api_key(client: httpx.AsyncClient) -> None:
    uid = await make_user()
    _, raw = await make_key(uid, ["sources:read"])
    r = await client.post("/_t/echo", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200 and r.json() == {"id": uid}
    # a bad ih_ bearer is 401 and never falls through to JWT verification
    r = await client.post("/_t/echo", headers={"Authorization": f"Bearer {raw}x"})
    assert r.status_code == 401
    r = await client.post("/_t/echo", headers={"Authorization": "Bearer ih_garbage"})
    assert r.status_code == 401


async def test_bearer_revoked_or_expired_key_401(client: httpx.AsyncClient) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.engine import session_scope
    from app.db.models import ApiKey

    uid = await make_user("b")
    _, expired = await make_key(uid, [], datetime.now(UTC) - timedelta(minutes=1))
    kid, revoked = await make_key(uid, [])
    async with session_scope() as s:
        k = await s.get(ApiKey, kid)
        assert k
        k.revoked = True
    for raw in (expired, revoked):
        r = await client.post("/_t/echo", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401
