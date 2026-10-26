from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fake_idp
import httpx
import pytest
import respx
from fastapi import Depends, FastAPI
from pydantic import SecretStr

from app.auth.deps import current_principal, require_admin
from app.auth.principal import Principal
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        master_key=SecretStr("test-master-key-0123456789abcdef-xyz"),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
        public_url="http://testserver",
        oidc_issuer=fake_idp.ISSUER,
        oidc_client_id=fake_idp.CLIENT_ID,
        oidc_client_secret=SecretStr("client-secret"),
    )


@pytest.fixture
def idp() -> AsyncIterator[fake_idp.FakeIdp]:  # type: ignore[misc]
    idp = fake_idp.FakeIdp()
    with respx.mock(assert_all_called=False) as router:
        idp.mount(router)
        yield idp  # type: ignore[misc]


@pytest.fixture
async def app(settings: Settings, idp: fake_idp.FakeIdp) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    app.state.runtime_enabled = False

    @app.post("/_t/echo")
    async def echo(p: Principal = Depends(current_principal)) -> dict[str, int]:
        return {"id": p.user_id}

    @app.get("/_t/admin")
    async def admin(_p: Principal = Depends(require_admin)) -> dict[str, bool]:
        return {"ok": True}

    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


async def do_login(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp, sub: str, groups: list[str]
) -> httpx.Response:
    r = await client.get("/api/v1/auth/login")
    assert r.status_code in (302, 307)
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"]
    idp.nonce = q["nonce"][0]
    idp.next_claims = {"sub": sub, "groups": groups}
    return await client.get("/api/v1/auth/callback", params={"code": "abc", "state": q["state"][0]})
