import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select

from app.api.v1 import sources as sources_api
from app.core.config import Settings
from app.core.crypto import SecretBox
from app.db.engine import session_scope
from app.db.models import (
    BackfillMode,
    Credential,
    CredentialKind,
    ImmichTarget,
    Setting,
    Source,
    User,
)
from app.rip.build import build_snapshots
from app.rip.filters import FilterSpec, check_meta
from app.rip.preview import PreviewItem, preview, run_in_subprocess
from app.rip.settings import RateLimit, RipSettings
from app.rip.snapshot import SourceSnapshot

sys.path.insert(0, str(Path(__file__).parent.parent / "api"))
from helpers import TARGET, actor  # noqa: E402

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("posix only", allow_module_level=True)


def _src(url: str, filters: FilterSpec | None = None) -> SourceSnapshot:
    return SourceSnapshot(
        id=0,
        name="p",
        url=url,
        extractor="directlink",
        target_id=1,
        album_template="",
        backfill_mode=BackfillMode.full,
        backfill_value=None,
        allow_animated=False,
        filters=filters or FilterSpec(),
        gdl_options={},
        proxy=None,
        log_level="info",
    )


def _settings(tmp_path: Path) -> RipSettings:
    return RipSettings(
        allow_private_hosts=True,
        rate_limits={"default": RateLimit(sleep_request=0, sleep=0, retries=0)},
    )


def test_preview_lists_items_from_local_server(img_server: str, tmp_path: Path) -> None:
    items = preview(
        _src(f"{img_server}/img/a.jpg"), None, _settings(tmp_path), scratch=tmp_path / "s"
    )
    assert len(items) == 1
    assert items[0].filename == "a" and items[0].verdict is None
    assert items[0].url.endswith("/img/a.jpg")
    assert list((tmp_path / "s").iterdir()) == []


def test_preview_title_filter_verdict(img_server: str, tmp_path: Path) -> None:
    f = FilterSpec(title_include="zzz")
    items = preview(
        _src(f"{img_server}/img/a.jpg", f), None, _settings(tmp_path), scratch=tmp_path / "s"
    )
    assert items[0].verdict == "title_not_included"


def test_preview_limit(img_server: str, tmp_path: Path) -> None:
    s = _src(f"r:{img_server}/page/two")
    s.extractor = "recursive"
    items = preview(s, None, _settings(tmp_path), tmp_path / "s", limit=1)
    assert len(items) == 1


def test_check_meta_date() -> None:
    from datetime import datetime

    spec = FilterSpec()
    assert check_meta({"date": datetime(2020, 1, 1)}, spec) is None
    assert (
        check_meta({"date": datetime(2020, 1, 1)}, spec, since=datetime(2021, 1, 1).date())
        == "date_out_of_range"
    )


def test_subprocess_timeout_kills() -> None:
    import time

    t = time.monotonic()
    with pytest.raises(TimeoutError):
        run_in_subprocess(time.sleep, 30, timeout=1.0)
    assert time.monotonic() - t < 15


def test_subprocess_error_is_preview_error() -> None:
    from app.rip.preview import PreviewError

    with pytest.raises(PreviewError):
        run_in_subprocess(int, "x", timeout=30)


def test_subprocess_returns() -> None:
    assert run_in_subprocess(abs, -3, timeout=30) == 3


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        master_key=SecretStr("test-master-key-0123456789abcdef-xyz"),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
        public_url="http://testserver",
        scratch_dir=tmp_path / "scratch",
    )


async def _mk_target(h: dict[str, str], c: httpx.AsyncClient) -> int:
    return (await c.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]


async def test_preview_endpoint_ok(client: httpx.AsyncClient, img_server: str) -> None:
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    async with session_scope() as s:
        s.add(Setting(key="rip", value={"allow_private_hosts": True}))
    r = await client.post(
        "/api/v1/sources/preview",
        json={"name": "p", "url": f"{img_server}/img/a.jpg", "target_id": tid, "limit": 5},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["filename"] == "a"


async def test_preview_endpoint_limit_cap_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    r = await client.post(
        "/api/v1/sources/preview",
        json={"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid, "limit": 51},
        headers=h,
    )
    assert r.status_code == 422


async def test_preview_timeout_504(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: object, **k: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(sources_api, "run_in_subprocess", boom)
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    r = await client.post(
        "/api/v1/sources/preview",
        json={"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
        headers=h,
    )
    assert r.status_code == 504 and r.json() == {"detail": "preview timed out"}


async def test_preview_failure_502_no_secret(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.rip.preview import PreviewError

    def boom(*a: object, **k: object) -> None:
        raise PreviewError("x" * 500)

    monkeypatch.setattr(sources_api, "run_in_subprocess", boom)
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    r = await client.post(
        "/api/v1/sources/preview",
        json={"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
        headers=h,
    )
    assert r.status_code == 502
    assert r.json()["detail"] == "preview failed: " + "x" * 200


async def test_preview_requires_use_on_credential(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    _, hb = await actor("b")
    c = await client.post(
        "/api/v1/credentials",
        json={"name": "c", "site": "reddit", "kind": "cookies", "secret": "x"},
        headers=ha,
    )
    cid = c.json()["id"]
    tid = await _mk_target(hb, client)
    r = await client.post(
        "/api/v1/sources/preview",
        json={
            "name": "p",
            "url": "https://www.reddit.com/r/pics/",
            "target_id": tid,
            "credential_id": cid,
        },
        headers=hb,
    )
    assert r.status_code == 403


async def test_build_snapshots_rechecks_access(client: httpx.AsyncClient, settings: object) -> None:
    box = SecretBox("test-master-key-0123456789abcdef-xyz")
    async with session_scope() as s:
        owner = User(sub="o")
        other = User(sub="x")
        s.add_all([owner, other])
        await s.flush()
        t = ImmichTarget(
            owner_id=other.id, name="t", url="http://i", api_key_enc=box.encrypt(b"key")
        )
        s.add(t)
        await s.flush()
        src = Source(owner_id=owner.id, name="s", url="http://s", extractor="x", target_id=t.id)
        s.add(src)
        await s.flush()
        with pytest.raises(HTTPException) as e:
            await build_snapshots(s, src, box)
        assert e.value.status_code == 403
        t.owner_id = owner.id
        cred = Credential(
            owner_id=other.id,
            name="c",
            site="reddit",
            kind=CredentialKind.cookies,
            secret_enc=box.encrypt(b"sek"),
        )
        s.add(cred)
        await s.flush()
        src.credential_id = cred.id
        with pytest.raises(HTTPException) as e2:
            await build_snapshots(s, src, box)
        assert e2.value.status_code == 403
        cred.owner_id = owner.id
        snap, tsnap, csnap = await build_snapshots(s, src, box)
        assert tsnap.api_key.get_secret_value() == "key"
        assert csnap is not None and csnap.secret.get_secret_value() == "sek"
        assert snap.log_level == "info"
        owner.disabled = True
        with pytest.raises(HTTPException) as e3:
            await build_snapshots(s, src, box)
        assert e3.value.status_code == 403
    assert select and SecretStr and PreviewItem
