import os
import sqlite3
from pathlib import Path

import httpx
import pytest
from helpers import TARGET, actor, headers_for
from sqlalchemy import select

from app.core.config import Settings
from app.db.engine import session_scope
from app.db.models import Job, JobStatus, Role, User
from app.main import create_app
from app.runtime import maintenance
from app.runtime.maintenance import (
    apply_pending_restore,
    pending_path,
    resolve_backup,
    revert_restore,
)

B = "/api/v1/admin/backups"
PENDING = "restore-pending.db"


async def _admin() -> dict[str, str]:
    aid, _ = await actor("adm", Role.admin)
    return await headers_for(aid)


async def _backup(c: httpx.AsyncClient, h: dict[str, str]) -> str:
    r = await c.post("/api/v1/admin/backup", headers=h)
    assert r.status_code == 201
    return str(r.json()["file"])


def _targets(settings: Settings) -> int:
    db = settings.database_url.split("///", 1)[1]
    con = sqlite3.connect(db)
    try:
        return int(con.execute("SELECT count(*) FROM immich_targets").fetchone()[0])
    finally:
        con.close()


def _pending(settings: Settings) -> Path:
    p = pending_path(settings.database_url)
    assert p is not None
    return p


def test_resolve_backup_rejects_traversal(tmp_path: Path) -> None:
    d = tmp_path / "b"
    d.mkdir()
    good = d / "hoarder-20260101-000000.db"
    good.write_bytes(b"x")
    outside = tmp_path / "hoarder-20260101-000001.db"
    outside.write_bytes(b"x")
    (d / "hoarder-20260101-000002.db").symlink_to(outside)
    assert resolve_backup(d, good.name) == good
    for bad in (
        "../hoarder-20260101-000001.db",
        "..%2fx",
        "/etc/passwd",
        str(outside),
        "hoarder-20260101-000002.db",  # symlink
        "hoarder-20260101-000009.db",  # missing
        "hoarder-20260101-000000.db/",
        "restore-pending.db",
        "",
    ):
        assert resolve_backup(d, bad) is None, bad


async def test_traversal_and_auth_over_http(client: httpx.AsyncClient) -> None:
    h = await _admin()
    _, hu = await actor("u")
    for path in ("..%2f..%2fetc%2fpasswd", "%2e%2e%2fx", "nope.db", "hoarder-1.db"):
        assert (await client.get(f"{B}/{path}", headers=h)).status_code in (404, 422)
        assert (await client.delete(f"{B}/{path}", headers=h)).status_code in (404, 422)
        r = await client.post(f"{B}/{path}/restore", headers=h)
        assert r.status_code in (404, 422)
    name = await _backup(client, h)
    assert (await client.get(f"{B}/{name}", headers=hu)).status_code == 403
    assert (await client.delete(f"{B}/{name}", headers=hu)).status_code == 403
    assert (await client.post(f"{B}/{name}/restore", headers=hu)).status_code == 403
    assert (await client.delete(f"{B}/pending-restore", headers=hu)).status_code == 403


async def test_download_and_delete(client: httpx.AsyncClient, settings: Settings) -> None:
    h = await _admin()
    name = await _backup(client, h)
    r = await client.get(f"{B}/{name}", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"SQLite format 3")
    assert name in r.headers["content-disposition"]
    assert (await client.delete(f"{B}/{name}", headers=h)).status_code == 204
    assert not (settings.backup_dir / name).exists()
    assert (await client.get(f"{B}/{name}", headers=h)).status_code == 404
    assert (await client.delete(f"{B}/{name}", headers=h)).status_code == 404


async def test_restore_round_trip(client: httpx.AsyncClient, settings: Settings) -> None:
    h = await _admin()
    assert (await client.post("/api/v1/targets", json=TARGET, headers=h)).status_code == 201
    name = await _backup(client, h)
    tid = (await client.get("/api/v1/targets", headers=h)).json()["items"][0]["id"]
    assert (await client.delete(f"/api/v1/targets/{tid}", headers=h)).status_code == 204
    assert _targets(settings) == 0

    called: list[int] = []
    client._transport.app.state.shutdown = lambda: called.append(1)  # type: ignore[attr-defined]
    r = await client.post(f"{B}/{name}/restore?restart=true", headers=h)
    assert r.status_code == 202
    assert r.json() == {"restart_required": True, "restarting": True}
    assert called == [1]
    assert (await client.get(B, headers=h)).json()["restore_pending"] is True
    assert _targets(settings) == 0  # live DB untouched until restart

    res = apply_pending_restore(settings.database_url)
    assert res is not None and res.saved is not None and res.saved.exists()
    assert _targets(settings) == 1
    assert not _pending(settings).exists()


async def test_cancel_pending(client: httpx.AsyncClient, settings: Settings) -> None:
    h = await _admin()
    name = await _backup(client, h)
    assert (await client.delete(f"{B}/pending-restore", headers=h)).status_code == 404
    assert (await client.post(f"{B}/{name}/restore", headers=h)).json()["restarting"] is False
    assert (await client.delete(f"{B}/pending-restore", headers=h)).status_code == 204
    assert apply_pending_restore(settings.database_url) is None
    assert (await client.get(B, headers=h)).json()["restore_pending"] is False


async def test_restore_409_with_active_job(client: httpx.AsyncClient, settings: Settings) -> None:
    h = await _admin()
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    sid = (
        await client.post(
            "/api/v1/sources",
            json={"name": "s", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
            headers=h,
        )
    ).json()["id"]
    name = await _backup(client, h)
    async with session_scope() as s:
        s.add(Job(source_id=sid, status=JobStatus.running))
    r = await client.post(f"{B}/{name}/restore", headers=h)
    assert r.status_code == 409
    assert not _pending(settings).exists()


async def test_restore_409_non_sqlite(client: httpx.AsyncClient, settings: Settings) -> None:
    h = await _admin()
    name = await _backup(client, h)
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.settings = settings.model_copy(
        update={"database_url": "postgresql+asyncpg://u:p@localhost/db"}
    )
    r = await client.post(f"{B}/{name}/restore", headers=h)
    assert r.status_code == 409


async def test_restore_rejects_corrupt_backup(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    h = await _admin()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    bad = settings.backup_dir / "hoarder-20250101-000000.db"
    bad.write_bytes(b"not a database" * 100)
    r = await client.post(f"{B}/{bad.name}/restore", headers=h)
    assert r.status_code == 422
    assert not _pending(settings).exists()


async def test_corrupt_pending_keeps_original(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    h = await _admin()
    assert (await client.post("/api/v1/targets", json=TARGET, headers=h)).status_code == 201
    pend = _pending(settings)
    pend.write_bytes(b"garbage" * 500)
    assert apply_pending_restore(settings.database_url) is None
    assert not pend.exists()
    assert _targets(settings) == 1


async def test_crash_mid_apply_recovers_original(
    client: httpx.AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await _admin()
    name = await _backup(client, h)
    assert (await client.post("/api/v1/targets", json=TARGET, headers=h)).status_code == 201
    assert (await client.post(f"{B}/{name}/restore", headers=h)).status_code == 202
    pend = _pending(settings)
    real = os.replace

    def flaky(src: object, dst: object) -> None:
        if Path(str(src)) == pend:
            raise OSError("disk gone")
        real(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(maintenance.os, "replace", flaky)
    assert apply_pending_restore(settings.database_url) is None
    monkeypatch.undo()
    assert _targets(settings) == 1  # original (with the target) is back
    assert not pend.exists()
    assert not list(pend.parent.glob("pre-restore-*"))


async def test_revert_restore(client: httpx.AsyncClient, settings: Settings) -> None:
    h = await _admin()
    name = await _backup(client, h)
    assert (await client.post("/api/v1/targets", json=TARGET, headers=h)).status_code == 201
    await client.post(f"{B}/{name}/restore", headers=h)
    res = apply_pending_restore(settings.database_url)
    assert res is not None and res.saved is not None and _targets(settings) == 0
    revert_restore(settings.database_url, res.saved)
    assert _targets(settings) == 1


async def test_startup_applies_restore_and_bumps_sessions(settings: Settings) -> None:
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with app.router.lifespan_context(app):
        aid, _ = await actor("adm", Role.admin)
        async with session_scope() as s:
            u = await s.get(User, aid)
            assert u is not None
            before = u.session_gen
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            h = await headers_for(aid)
            name = await _backup(c, h)
            assert (await c.post(f"{B}/{name}/restore", headers=h)).status_code == 202
    app2 = create_app(settings)
    app2.state.runtime_enabled = False
    async with app2.router.lifespan_context(app2), session_scope() as s:
        row = (await s.execute(select(User.session_gen).where(User.id == aid))).scalar_one()
        assert row == before + 1
    assert list(_pending(settings).parent.glob("pre-restore-*"))


def _seed(path: Path, gen: int) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, session_gen INTEGER)")
    con.execute("INSERT INTO users VALUES (1, ?)", (gen,))
    con.commit()
    con.close()


def test_apply_reports_floor_and_handles_missing_original(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'live.db'}"
    _seed(tmp_path / "live.db", 4)
    _seed(tmp_path / PENDING, 3)
    res = apply_pending_restore(url)
    assert res is not None and res.session_floor == 4 and res.saved is not None
    # no original DB at all: still reported as applied, with nothing to revert to
    (tmp_path / "live.db").unlink()
    _seed(tmp_path / PENDING, 3)
    res = apply_pending_restore(url)
    assert res is not None and res.saved is None and res.session_floor == 0
    assert (tmp_path / "live.db").exists()
    revert_restore(url, tmp_path / "missing.db")  # no-op, must not raise


async def test_old_cookie_rejected_after_restore_with_lower_gen(settings: Settings) -> None:
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with app.router.lifespan_context(app):
        aid, _ = await actor("adm", Role.admin)
        async with session_scope() as s:
            u = await s.get(User, aid)
            assert u is not None
            u.session_gen = 0
        h = await headers_for(aid)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            name = await _backup(c, h)  # backup has gen 0
            assert (await c.post(f"{B}/{name}/restore", headers=h)).status_code == 202
        async with session_scope() as s:
            u = await s.get(User, aid)
            assert u is not None
            u.session_gen = 4  # live DB is ahead of the backup
    app2 = create_app(settings)
    app2.state.runtime_enabled = False
    async with app2.router.lifespan_context(app2), session_scope() as s:
        gen = (await s.execute(select(User.session_gen).where(User.id == aid))).scalar_one()
        assert gen == 5  # a cookie with sg=4 (or restored+1 == 1) no longer matches
