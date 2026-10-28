import hashlib
import json
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.engine import make_sync_engine
from app.db.models import (
    AssetSeen,
    BackfillMode,
    Base,
    CredentialKind,
    ImmichTarget,
    Source,
    User,
)
from app.immich.client import ImmichClient
from app.rip.dedupe import DedupeStore
from app.rip.filters import FilterSpec
from app.rip.media import analyze
from app.rip.pipeline import RipContext, RipResult, _Rip, build_description, run_rip, sweep_scratch
from app.rip.settings import RateLimit, RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot, TargetSnapshot

BASE = "http://immich.test/api"
ASSET = str(uuid.uuid4())
ALBUM = str(uuid.uuid4())


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = make_sync_engine(f"sqlite+aiosqlite:///{tmp_path / 'd.db'}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(sub="u1")
        s.add(u)
        s.flush()
        t = ImmichTarget(owner_id=u.id, name="t", url="http://immich.test", api_key_enc=b"x")
        s.add(t)
        s.flush()
        s.add(Source(owner_id=u.id, name="s", url="http://s", extractor="x", target_id=t.id))
        s.commit()
    yield eng
    eng.dispose()


class Env:
    def __init__(self, tmp_path: Path, engine: Engine, router: respx.MockRouter, base: str):
        self.scratch = tmp_path / "scratch"
        self.scratch.mkdir()
        self.store = DedupeStore(engine)
        self.router = router
        self.base = base
        self.events: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.uploads: list[str] = []
        self.linked: list[str] = []
        self.peak_files = 0
        self.active = 0
        self.upload_delay = 0.0
        self.on_upload: Callable[[], None] = lambda: None
        router.post(f"{BASE}/assets/bulk-upload-check").mock(side_effect=self._bulk)
        router.post(f"{BASE}/assets").mock(side_effect=self._upload)
        router.get(f"{BASE}/albums").mock(return_value=httpx.Response(200, json=[]))
        router.post(f"{BASE}/albums").mock(
            return_value=httpx.Response(200, json={"id": ALBUM, "albumName": "x", "assetCount": 0})
        )
        router.put(f"{BASE}/albums/{ALBUM}/assets").mock(side_effect=self._add)
        router.put(url__regex=rf"{BASE}/assets/.+").mock(return_value=httpx.Response(200, json={}))
        self.bulk_response: Callable[[str], dict[str, Any]] = lambda i: {
            "id": i,
            "action": "accept",
        }
        self.add_error: str | None = None

    def _bulk(self, request: httpx.Request) -> httpx.Response:
        items = json.loads(request.content)["assets"]
        return httpx.Response(200, json={"results": [self.bulk_response(a["id"]) for a in items]})

    def _upload(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.active += 1
            self.peak_files = max(self.peak_files, self.active)
        self.on_upload()
        time.sleep(self.upload_delay)
        with self.lock:
            self.active -= 1
        aid = str(uuid.uuid4())
        with self.lock:
            self.uploads.append(aid)
        return httpx.Response(201, json={"id": aid, "status": "created"})

    def _add(self, request: httpx.Request) -> httpx.Response:
        ids = json.loads(request.content)["ids"]
        with self.lock:
            self.linked.extend(ids)
        out = [
            {
                "id": i,
                "success": self.add_error is None,
                **({"error": self.add_error} if self.add_error else {}),
            }
            for i in ids
        ]
        return httpx.Response(200, json=out)

    def emit(self, ev: dict[str, Any]) -> None:
        with self.lock:
            self.events.append(ev)

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]

    def run(
        self,
        path: str,
        *,
        extractor: str = "directlink",
        filters: FilterSpec | None = None,
        concurrency: int = 4,
        cap: int = 10**9,
        incremental: bool = False,
        client_factory: Callable[[TargetSnapshot], ImmichClient] | None = None,
        credential: CredentialSnapshot | None = None,
    ) -> RipResult:
        url = f"{self.base}{path}"
        if extractor == "recursive":
            url = f"r:{url}"
        src = SourceSnapshot(
            id=1,
            name="s",
            url=url,
            extractor=extractor,
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
        settings = RipSettings(
            allow_private_hosts=True,
            upload_concurrency=concurrency,
            rate_limits={"default": RateLimit(sleep_request=0, sleep=0, retries=0)},
        )
        ctx = RipContext(
            job_id=7,
            source=src,
            target=TargetSnapshot(id=1, url="http://immich.test", api_key=SecretStr("k")),
            credential=credential,
            settings=settings,
            scratch_dir=self.scratch,
            scratch_cap_bytes=cap,
            incremental=incremental,
            store=self.store,
            recorder=self.store,
            client_factory=client_factory
            or (lambda t: ImmichClient(t.url, t.api_key.get_secret_value(), sleep=lambda s: None)),
        )
        return run_rip(ctx, self.emit, self.cancel)


@pytest.fixture
def env(tmp_path: Path, engine: Engine, img_server: str) -> Iterator[Env]:
    with respx.mock(assert_all_called=False) as router:
        yield Env(tmp_path, engine, router, img_server)


def fetch(env: Env, path: str) -> bytes:
    with urllib.request.urlopen(env.base + path) as r:  # noqa: S310
        return bytes(r.read())


def a_info(env: Env, tmp_path: Path) -> Any:
    p = tmp_path / "a.jpg"
    p.write_bytes(fetch(env, "/img/a.jpg"))
    return analyze(p)


def _rows(engine: Engine) -> int:
    with engine.connect() as c:
        return int(c.execute(select(func.count()).select_from(AssetSeen)).scalar() or 0)


def test_new_image_uploaded_linked_described_recorded(env: Env) -> None:
    r = env.run("/img/a.jpg")
    assert r.status == "succeeded" and r.error is None
    assert r.counters["uploaded"] == 1
    assert len(env.uploads) == 1 and env.linked == env.uploads
    sha1 = hashlib.sha1(fetch(env, "/img/a.jpg")).digest()
    ref = env.store.match_sha1(1, sha1)
    assert ref is not None and ref.immich_asset_id == env.uploads[0]
    t = env.types()
    assert t[0] == "phase" and t[-1] == "phase" and "item.uploaded" in t and "progress" in t
    phases = [e["name"] for e in env.events if e["type"] == "phase"]
    assert phases == ["starting", "extracting", "draining", "done"]
    assert not any(env.scratch.iterdir())


def test_local_sha1_duplicate_links_without_upload(env: Env) -> None:
    sha1 = hashlib.sha1(fetch(env, "/img/a.jpg")).digest()
    env.store.record(
        target_id=1, source_id=1, key=b"k" * 16, sha1=sha1, phash=None, immich_asset_id=ASSET
    )
    r = env.run("/img/a.jpg")
    assert r.counters["linked"] == 1 and env.uploads == []
    assert env.linked == [ASSET]
    ev = [e for e in env.events if e["type"] == "item.linked"]
    assert ev and ev[0]["duplicate"] is True and "item.duplicate" not in env.types()


def test_phash_near_duplicate_links(env: Env, tmp_path: Path) -> None:
    info = a_info(env, tmp_path)
    env.store.record(
        target_id=1,
        source_id=1,
        key=b"k" * 16,
        sha1=b"\x01" * 20,
        phash=info.phash ^ 1,
        immich_asset_id=ASSET,
    )
    env.run("/img/a.jpg")
    assert env.uploads == [] and env.linked == [ASSET]


def test_bulk_check_trashed_is_deleted_in_immich_not_uploaded(env: Env) -> None:
    env.bulk_response = lambda i: {
        "id": i,
        "action": "reject",
        "reason": "duplicate",
        "assetId": ASSET,
        "isTrashed": True,
    }
    r = env.run("/img/a.jpg")
    assert r.counters["deleted_in_immich"] == 1
    assert env.uploads == [] and env.linked == []
    assert "item.deleted_in_immich" in env.types()
    sha1 = hashlib.sha1(fetch(env, "/img/a.jpg")).digest()
    assert env.store.match_sha1(1, sha1) is None


def test_bulk_check_duplicate_links_existing(env: Env) -> None:
    env.bulk_response = lambda i: {
        "id": i,
        "action": "reject",
        "reason": "duplicate",
        "assetId": ASSET,
    }
    env.run("/img/a.jpg")
    assert env.uploads == [] and env.linked == [ASSET]


def test_album_add_not_found_then_gone_is_deleted_in_immich(env: Env) -> None:
    env.add_error = "not_found"
    env.router.get(url__regex=rf"{BASE}/assets/.+").mock(
        return_value=httpx.Response(404, json={"message": "gone"})
    )
    r = env.run("/img/a.jpg")
    assert r.counters["deleted_in_immich"] == 1 and r.counters["uploaded"] == 0
    assert "item.deleted_in_immich" in env.types()


def test_album_add_error_not_gone_fails_and_records_nothing(env: Env, engine: Engine) -> None:
    env.add_error = "no_permission"
    env.router.get(url__regex=rf"{BASE}/assets/.+").mock(
        return_value=httpx.Response(200, json={"id": ASSET, "isTrashed": False})
    )
    r = env.run("/img/a.jpg")
    assert r.counters["failed"] == 1 and r.status == "succeeded"
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(AssetSeen)).scalar() == 0


def test_corrupt_image_filtered_not_an_image_key_only(env: Env, engine: Engine) -> None:
    r = env.run("/img/corrupt.jpg")
    ev = [e for e in env.events if e["type"] == "item.filtered"]
    assert r.counters["filtered"] == 1 and ev[0]["reason"] == "not_an_image"
    assert env.uploads == [] and not any(env.scratch.iterdir())
    with engine.connect() as c:
        rows = c.execute(select(AssetSeen.sha1, AssetSeen.phash, AssetSeen.immich_asset_id)).all()
    assert len(rows) == 1 and tuple(rows[0]) == (None, None, None)


def test_filtered_records_key_only_and_not_redownloaded_next_run(env: Env) -> None:
    f = FilterSpec(min_width=1000)
    r = env.run("/img/a.jpg", filters=f)
    assert r.counters["filtered"] == 1 and env.uploads == []
    ev = [e for e in env.events if e["type"] == "item.filtered"]
    assert ev[0]["reason"] == "too_small"
    env.events.clear()
    r2 = env.run("/img/a.jpg", filters=f)
    assert "item.filtered" not in env.types() and r2.counters["filtered"] == 0
    sha1 = hashlib.sha1(fetch(env, "/img/a.jpg")).digest()
    assert env.store.match_sha1(1, sha1) is None


def test_upload_failure_not_recorded_and_file_deleted(env: Env) -> None:
    env.router.post(f"{BASE}/assets").mock(
        return_value=httpx.Response(400, json={"message": "bad"})
    )
    r = env.run("/img/a.jpg")
    assert r.status == "succeeded" and r.counters["failed"] == 1
    ev = [e for e in env.events if e["type"] == "item.failed"]
    assert ev[0]["reason"] == "immich_error"
    sha1 = hashlib.sha1(fetch(env, "/img/a.jpg")).digest()
    assert env.store.match_sha1(1, sha1) is None
    assert not any(env.scratch.iterdir())


def test_same_image_twice_in_run_uploaded_once(env: Env) -> None:
    env.upload_delay = 0.4
    r = env.run("/page/dup", extractor="recursive", concurrency=4)
    assert len(env.uploads) == 1
    assert r.counters["uploaded"] == 1 and r.counters["linked"] == 1
    assert env.linked == [env.uploads[0]] * 2


def test_immich_unavailable_items_failed_job_finishes(env: Env, engine: Engine) -> None:
    env.router.post(f"{BASE}/assets/bulk-upload-check").mock(return_value=httpx.Response(503))
    r = env.run("/img/a.jpg")
    assert r.status == "succeeded" and r.counters["failed"] == 1
    ev = [e for e in env.events if e["type"] == "item.failed"]
    assert ev[0]["reason"] == "immich_unavailable"
    assert _rows(engine) == 0 and not any(env.scratch.iterdir())


def test_auth_error_fails_job(env: Env, engine: Engine) -> None:
    env.router.post(f"{BASE}/assets/bulk-upload-check").mock(
        return_value=httpx.Response(401, json={"message": "no"})
    )
    r = env.run("/page/two", extractor="recursive")
    assert r.status == "failed" and r.error == "immich unauthorized"
    assert _rows(engine) == 0
    assert not any(env.scratch.iterdir())


@pytest.mark.parametrize("mode", ["success", "failure", "cancel"])
def test_scratch_empty_after_success_failure_and_cancel(env: Env, mode: str) -> None:
    if mode == "failure":
        env.router.post(f"{BASE}/assets").mock(return_value=httpx.Response(400, json={}))
    if mode == "cancel":
        env.on_upload = env.cancel.set
    r = env.run("/page/two", extractor="recursive", concurrency=1)
    assert r.status == ("cancelled" if mode == "cancel" else "succeeded")
    assert not any(env.scratch.iterdir())


def test_backpressure_blocks_when_over_cap(env: Env) -> None:
    env.upload_delay = 0.2
    r = env.run("/page/two", extractor="recursive", concurrency=4, cap=1)
    assert r.counters["uploaded"] == 2
    assert env.peak_files <= 1


def test_no_cap_uploads_concurrently(env: Env) -> None:
    env.upload_delay = 0.4
    env.run("/page/two", extractor="recursive", concurrency=4)
    assert env.peak_files == 2


def test_sweep_scratch_removes_orphans_only(tmp_path: Path) -> None:
    for n in ("1", "2", "3"):
        (tmp_path / n).mkdir()
        (tmp_path / n / "f").write_bytes(b"x")
    (tmp_path / "keep.txt").write_text("x")
    assert sweep_scratch(tmp_path, {2}) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2", "keep.txt"]


def test_build_description() -> None:
    d = build_description({"title": "T", "permalink": "/r/x/1", "author": "bob"})
    assert d == "T\nhttps://www.reddit.com/r/x/1\nby bob"
    assert build_description({"url": "http://u"}) == "http://u"
    assert build_description({}) == ""
    assert len(build_description({"title": "x" * 5000})) == 2000


def test_description_falls_back_to_file_url() -> None:
    assert build_description({"_file_url": "http://site/a.jpg"}) == "http://site/a.jpg"
    assert build_description({"url": "http://u", "_file_url": "http://f"}) == "http://u"


@pytest.mark.parametrize(
    "raw",
    [
        "http://site/a.jpg?X-Amz-Signature=abc&X-Amz-Credential=k",
        "http://site/a.jpg?token=secret",
        "http://user:pw@site/a.jpg",
        "http://site/a.jpg#frag",
    ],
)
def test_file_url_is_scrubbed(raw: str) -> None:
    d = build_description({"_file_url": raw})
    assert d == "http://site/a.jpg"
    assert _Rip._url({"_file_url": raw}, None) == "http://site/a.jpg"
    assert build_description({"_file_url": "http://h:81/p/a.jpg?x=1"}) == "http://h:81/p/a.jpg"


def test_gdl_error_and_all_uploads_failing_is_failed(env: Env) -> None:
    env.router.post(f"{BASE}/assets").mock(return_value=httpx.Response(400, json={}))
    r = env.run("/page/bad", extractor="recursive")
    assert r.counters["failed"] >= 1 and r.status == "failed"


def test_deleted_exact_copy_from_new_url_not_reuploaded(env: Env) -> None:
    env.bulk_response = lambda i: {
        "id": i,
        "action": "reject",
        "reason": "duplicate",
        "assetId": ASSET,
        "isTrashed": True,
    }
    env.run("/img/a.jpg")
    env.bulk_response = lambda i: {"id": i, "action": "accept"}  # trash emptied
    env.events.clear()
    r = env.run("/img/a2.jpg")
    assert r.counters["deleted_in_immich"] == 1 and env.uploads == []


def test_deleted_near_copy_from_new_url_not_reuploaded(env: Env, tmp_path: Path) -> None:
    info = a_info(env, tmp_path)
    env.store.record(
        target_id=1,
        source_id=1,
        key=b"k" * 16,
        sha1=b"\x01" * 20,
        phash=info.phash ^ 1,
        immich_asset_id=None,
    )
    r = env.run("/img/a.jpg")
    assert r.counters["deleted_in_immich"] == 1 and env.uploads == []


def test_scratch_empty_when_gallery_dl_raises(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.rip.pipeline.run_job", boom)
    r = env.run("/img/a.jpg")
    assert r.status == "failed" and not any(env.scratch.iterdir())


def test_client_factory_failure_cleans_job_dir_and_fails(env: Env) -> None:
    def boom(_t: TargetSnapshot) -> ImmichClient:
        raise RuntimeError("no client")

    r = env.run("/page/two", extractor="recursive", client_factory=boom)
    assert r.status == "failed"
    assert not any(env.scratch.iterdir())


def test_pipeline_crash_log_is_scrubbed(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> int:
        raise RuntimeError("bad ?api_key=zzSECRETzz")

    monkeypatch.setattr("app.rip.pipeline.run_job", boom)
    cred = CredentialSnapshot(
        site="x", kind=CredentialKind.token, secret=SecretStr('{"refresh-token": "zzSECRETzz"}')
    )
    env.run("/img/a.jpg", credential=cred)
    logs = json.dumps([e for e in env.events if e["type"] == "log"])
    assert "***" in logs and "zzSECRETzz" not in logs


def test_events_comment_has_no_item_duplicate() -> None:
    import app.rip.events as events

    assert "item.duplicate" not in Path(events.__file__).read_text()


def test_queued_item_after_cancel_fails_deterministically(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.rip import pipeline

    entered, release = threading.Event(), threading.Event()
    submitted = threading.Semaphore(0)
    calls: list[int] = []

    def block() -> None:
        calls.append(1)
        entered.set()
        assert release.wait(20)

    env.on_upload = block
    orig = pipeline._Rip.on_file

    def on_file(self: Any, path: Path, meta: dict[str, Any]) -> None:
        orig(self, path, meta)
        submitted.release()

    monkeypatch.setattr(pipeline._Rip, "on_file", on_file)
    out: list[RipResult] = []
    t = threading.Thread(
        target=lambda: out.append(env.run("/page/two", extractor="recursive", concurrency=1))
    )
    t.start()
    try:
        assert entered.wait(20)  # first item holds the only pool thread
        assert submitted.acquire(timeout=20) and submitted.acquire(timeout=20)
        env.cancel.set()
    finally:
        release.set()
        t.join(30)
    assert not t.is_alive()
    assert len(calls) == 1
    failed = [e for e in env.events if e["type"] == "item.failed"]
    assert [e["reason"] for e in failed] == ["cancelled"]
    assert out[0].status == "cancelled"
    assert not any(env.scratch.iterdir())


def test_blocked_by_network_security_gives_hint(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    import logging

    def fake(job: Any, src: Any, settings: Any) -> int:
        logging.getLogger("gallery-dl").error("403 blocked by network security")
        return 4

    monkeypatch.setattr("app.rip.pipeline.run_job", fake)
    r = env.run("/img/a.jpg")
    assert r.status == "failed" and r.error and "TLS fingerprints" in r.error


def test_reddit_cookies_missing_session_fails_with_message(env: Env) -> None:
    cred = CredentialSnapshot(
        site="reddit",
        kind=CredentialKind.cookies,
        secret=SecretStr(".reddit.com\tTRUE\t/\tTRUE\t0\tloid\tabc\n"),
    )
    r = env.run("/img/a.jpg", credential=cred)
    assert r.status == "failed" and r.error and "missing reddit_session" in r.error
