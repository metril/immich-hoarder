import asyncio
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

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
from app.rip.pipeline import sweep_scratch
from app.rip.preview import (
    PreviewError,
    PreviewItem,
    make_job_dir,
    preview,
    run_in_subprocess,
)
from app.rip.settings import RateLimit, RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot

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


def _run(
    src: SourceSnapshot,
    tmp_path: Path,
    cred: CredentialSnapshot | None = None,
    limit: int = 50,
) -> list[PreviewItem]:
    d = make_job_dir(tmp_path / "s")
    try:
        return preview(src, cred, _settings(tmp_path), d, limit)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_preview_lists_items_from_local_server(img_server: str, tmp_path: Path) -> None:
    items = _run(_src(f"{img_server}/img/a.jpg"), tmp_path)
    assert len(items) == 1
    assert items[0].filename == "a" and items[0].verdict is None
    assert items[0].url.endswith("/img/a.jpg")
    assert list((tmp_path / "s").iterdir()) == []


def test_preview_title_filter_verdict(img_server: str, tmp_path: Path) -> None:
    f = FilterSpec(title_include="zzz")
    items = _run(_src(f"{img_server}/img/a.jpg", f), tmp_path)
    assert items[0].verdict == "title_not_included"


def test_preview_limit(img_server: str, tmp_path: Path) -> None:
    s = _src(f"r:{img_server}/page/two")
    s.extractor = "recursive"
    items = _run(s, tmp_path, limit=1)
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
    assert r.status_code == 403 and r.json()["detail"] == "no access to credential"


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


def test_preview_since_flows_to_verdict(img_server: str, tmp_path: Path) -> None:
    from datetime import datetime

    from app.rip import preview as pv

    kw = {"date": datetime(2020, 1, 1), "url": "u", "filename": "f"}
    src = _src("http://x/")
    src.backfill_mode = BackfillMode.since
    src.backfill_value = "2021-01-01"
    assert pv._item(kw, src).verdict == "date_out_of_range"


def test_preview_nonzero_status_raises(img_server: str, tmp_path: Path) -> None:
    s = _src(f"r:{img_server}/nope")
    s.extractor = "recursive"
    with pytest.raises(PreviewError) as e:
        _run(s, tmp_path)
    assert str(e.value)


def test_preview_error_scrubs_secret(img_server: str, tmp_path: Path) -> None:
    from app.rip.preview import _summary

    cred = CredentialSnapshot(site="x", kind=CredentialKind.userpass, secret=SecretStr("hunter2"))
    assert "hunter2" not in _summary(["bad hunter2 here"], 1, cred)
    assert len(_summary(["x" * 500], 1, None)) <= 200


async def test_preview_404_is_502(
    client: httpx.AsyncClient, img_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_extractor(session: object, url: str) -> str:
        return "recursive"

    monkeypatch.setattr(sources_api, "_extractor_for", fake_extractor)
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    async with session_scope() as s:
        s.add(Setting(key="rip", value={"allow_private_hosts": True}))
    r = await client.post(
        "/api/v1/sources/preview",
        json={"name": "p", "url": f"r:{img_server}/nope", "target_id": tid},
        headers=h,
    )
    assert r.status_code == 502 and r.json()["detail"].startswith("preview failed: ")


def _slow_with_cookie(src: object, cred: object, rip: object, job_dir: Path, limit: int) -> None:
    (job_dir / ".cookies.txt").write_text("SECRET")
    time.sleep(60)


async def test_timeout_cleans_job_dir(
    client: httpx.AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sources_api, "preview", _slow_with_cookie)
    monkeypatch.setattr(sources_api, "PREVIEW_TIMEOUT", 3.0)
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    r = await client.post(
        "/api/v1/sources/preview",
        json={"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
        headers=h,
    )
    assert r.status_code == 504
    assert list(settings.scratch_dir.glob("preview-*")) == []


def test_sweep_preview_dirs(tmp_path: Path) -> None:
    old, fresh, cli = tmp_path / "preview-old", tmp_path / "preview-new", tmp_path / "cli-1"
    for d in (old, fresh, cli):
        d.mkdir()
    t = time.time() - 700
    os.utime(old, (t, t))
    os.utime(cli, (t, t))
    sweep_scratch(tmp_path, set())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cli-1", "preview-new"]


async def test_preview_429_when_busy(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = threading.Semaphore(0)
    release = threading.Event()

    def slow(*a: object, **k: object) -> list[object]:
        entered.release()
        release.wait(20)
        return []

    monkeypatch.setattr(sources_api, "run_in_subprocess", slow)
    monkeypatch.setattr(sources_api, "_PREVIEW_SEM", asyncio.Semaphore(2))
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    body = {"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid}

    async def post() -> httpx.Response:
        return await client.post("/api/v1/sources/preview", json=body, headers=h)

    t1, t2 = asyncio.create_task(post()), asyncio.create_task(post())
    for _ in range(2):
        assert await asyncio.to_thread(entered.acquire, True, 15)
    r3 = await post()
    release.set()
    assert r3.status_code == 429 and r3.json() == {"detail": "too many previews"}
    assert (await t1).status_code == 200 and (await t2).status_code == 200


def _raise_preview() -> None:
    from app.rip.preview import PreviewError

    raise PreviewError("boom")


def test_preview_error_message_has_no_doubled_prefix() -> None:
    from app.rip.preview import PreviewError

    with pytest.raises(PreviewError) as ei:
        run_in_subprocess(_raise_preview, timeout=30)
    assert str(ei.value) == "boom"
    with pytest.raises(PreviewError) as ei2:
        run_in_subprocess(int, "x", timeout=30)
    assert str(ei2.value).startswith("ValueError: ")


async def test_preview_rmtree_runs_off_the_event_loop(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    threads: list[str] = []
    real = shutil.rmtree

    def spy(path: object, *a: object, **k: object) -> None:
        threads.append(threading.current_thread().name)
        real(path, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(sources_api, "run_in_subprocess", lambda *a, **k: [])
    monkeypatch.setattr(sources_api.shutil, "rmtree", spy)
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    r = await client.post(
        "/api/v1/sources/preview",
        json={"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
        headers=h,
    )
    assert r.status_code == 200
    assert threads and threads[0] != threading.main_thread().name


async def test_preview_disconnect_keeps_slot_and_dir_until_child_done(
    client: httpx.AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import anyio

    entered = threading.Event()
    release = threading.Event()

    def slow(*a: object, **k: object) -> list[object]:
        entered.set()
        release.wait(20)
        return []

    sem = asyncio.Semaphore(1)
    monkeypatch.setattr(sources_api, "run_in_subprocess", slow)
    monkeypatch.setattr(sources_api, "_PREVIEW_SEM", sem)
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    scope = anyio.CancelScope()

    async def post() -> None:
        with scope:
            await client.post(
                "/api/v1/sources/preview",
                json={"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
                headers=h,
            )

    task = asyncio.create_task(post())
    assert await asyncio.to_thread(entered.wait, 15)
    scope.cancel()  # client disconnect
    await asyncio.sleep(0.3)
    assert sem.locked()
    assert len(list(settings.scratch_dir.glob("preview-*"))) == 1
    release.set()
    await asyncio.wait_for(task, 15)
    assert not sem.locked()
    assert list(settings.scratch_dir.glob("preview-*")) == []


async def test_preview_cancel_during_cleanup_still_releases(
    client: httpx.AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import anyio

    in_cleanup = threading.Event()
    real = shutil.rmtree

    def slow_rmtree(path: object, *a: object, **k: object) -> None:
        in_cleanup.set()
        time.sleep(0.3)
        real(path, *a, **k)  # type: ignore[arg-type]

    sem = asyncio.Semaphore(1)
    monkeypatch.setattr(sources_api, "run_in_subprocess", lambda *a, **k: [])
    monkeypatch.setattr(sources_api.shutil, "rmtree", slow_rmtree)
    monkeypatch.setattr(sources_api, "_PREVIEW_SEM", sem)
    _, h = await actor("a")
    tid = await _mk_target(h, client)
    scope = anyio.CancelScope()

    async def post() -> None:
        with scope:
            await client.post(
                "/api/v1/sources/preview",
                json={"name": "p", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
                headers=h,
            )

    task = asyncio.create_task(post())
    assert await asyncio.to_thread(in_cleanup.wait, 15)
    scope.cancel()  # disconnect while cleanup is running
    await asyncio.wait_for(task, 15)
    assert not sem.locked()
    assert list(settings.scratch_dir.glob("preview-*")) == []
