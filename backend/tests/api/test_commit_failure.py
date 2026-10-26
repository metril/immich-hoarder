import httpx
import pytest
from helpers import actor
from sqlalchemy.ext.asyncio import AsyncSession


async def test_commit_failure_in_dependency_yields_500(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, h = await actor("a")

    async def boom(self: AsyncSession) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", boom)
    app = client._transport.app  # type: ignore[attr-defined]
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/api/v1/sources", headers=h)
    assert r.status_code == 500
