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
