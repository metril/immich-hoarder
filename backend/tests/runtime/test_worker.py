import multiprocessing as mp
import queue
import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.db.engine import make_sync_engine
from app.db.models import BackfillMode, Base, ImmichTarget, Source, User
from app.rip.dedupe import DedupeStore, url_key
from app.rip.filters import FilterSpec
from app.rip.settings import RipSettings
from app.rip.snapshot import SourceSnapshot, TargetSnapshot
from app.runtime import worker as worker_mod
from app.runtime.worker import OverlayStore, WorkerSpec, worker_main


@pytest.fixture
def store(tmp_path: Path) -> DedupeStore:
    eng = make_sync_engine(f"sqlite:///{tmp_path / 's.db'}")
    Base.metadata.create_all(eng)
    return DedupeStore(eng)


ASSET = "11111111-1111-1111-1111-111111111111"
ASSET2 = "22222222-2222-2222-2222-222222222222"


def test_overlay_makes_records_visible_within_run(store: DedupeStore) -> None:
    q: queue.Queue[Any] = queue.Queue()
    ov = OverlayStore(store, q, 7)
    key = url_key("c", "k")
    sha = b"\x01" * 20
    assert not ov.url_seen(1, key)
    assert ov.match_sha1(1, sha) is None
    ov.record(target_id=1, source_id=1, key=key, sha1=sha, phash=0xF0F0, immich_asset_id=ASSET)
    ov.record(
        target_id=1,
        source_id=1,
        key=b"k2" * 8,
        sha1=b"\x02" * 20,
        phash=0xFFFF0,
        immich_asset_id=None,
    )
    assert ov.url_seen(1, key)
    assert not ov.url_seen(2, key)
    ref = ov.match_sha1(1, sha)
    assert ref is not None and ref.immich_asset_id == ASSET
    near = ov.match_phash(1, 0xF0F1, 2)
    assert near is not None and near.immich_asset_id == ASSET
    assert ov.match_phash(1, 0xF0F0 ^ 0xFFFF, 2) is None
    assert ov.match_deleted(1, b"\x02" * 20, None, None)
    assert ov.match_deleted(1, b"\x09" * 20, 0xFFFF1, 1)
    assert not ov.match_deleted(1, b"\x09" * 20, 0xFFFF1 ^ 0xFF, 1)
    msgs = [q.get_nowait() for _ in range(2)]
    assert msgs[0][0] == "record" and msgs[0][1]["immich_asset_id"] == ASSET


def test_overlay_falls_back_to_db(store: DedupeStore) -> None:
    with Session(store._engine) as ses, ses.begin():
        ses.add(User(id=1, sub="u"))
        ses.flush()
        ses.add(ImmichTarget(id=1, owner_id=1, name="t", url="http://i", api_key_enc=b"x"))
        ses.flush()
        ses.add(Source(id=1, owner_id=1, name="s", url="http://s", extractor="x", target_id=1))
    key = url_key("c", "db")
    DedupeStore.record(
        store,
        target_id=1,
        source_id=1,
        key=key,
        sha1=b"\x05" * 20,
        phash=None,
        immich_asset_id=ASSET2,
    )
    ov = OverlayStore(store, queue.Queue(), 1)
    assert ov.url_seen(1, key)
    ref = ov.match_sha1(1, b"\x05" * 20)
    assert ref is not None and ref.immich_asset_id == ASSET2


def _spec(tmp_path: Path) -> WorkerSpec:
    return WorkerSpec(
        job_id=5,
        source=SourceSnapshot(
            id=1,
            name="s",
            url="http://s",
            extractor="x",
            target_id=1,
            album_template="a",
            backfill_mode=BackfillMode.full,
            backfill_value=None,
            allow_animated=False,
            reupload_deleted=False,
            filters=FilterSpec(),
            gdl_options={},
            proxy=None,
            log_level="info",
        ),
        target=TargetSnapshot(id=1, url="http://i", api_key="k"),  # type: ignore[arg-type]
        credential=None,
        rip_settings=RipSettings(),
        scratch_dir=tmp_path,
        scratch_cap_bytes=1000,
        incremental=False,
        db_url=f"sqlite:///{tmp_path / 'w.db'}",
        log_level="info",
    )


class FakeQ(queue.Queue[Any]):
    def close(self) -> None:
        self.closed = True

    def join_thread(self) -> None:
        pass


def _drain(q: Any) -> list[Any]:
    out = []
    while True:
        try:
            m = q.get(timeout=2)
        except queue.Empty:
            return out
        out.append(m)
        if m[0] == "done":
            return out


def test_worker_sends_events_records_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(ctx: Any, emit: Any, cancel: threading.Event) -> Any:
        emit({"type": "phase", "name": "starting"})
        ctx.recorder.record(
            target_id=1, source_id=1, key=b"k" * 16, sha1=None, phash=None, immich_asset_id=None
        )
        assert ctx.store.url_seen(1, b"k" * 16)
        assert cancel.wait(3)  # mp cancel is bridged to the threading event
        return worker_mod.RipResult(counters={"linked": 2}, status="cancelled", error=None)

    monkeypatch.setattr(worker_mod, "run_rip", fake_run)
    ctx = mp.get_context("spawn")
    q = FakeQ()
    cancel = ctx.Event()
    Base.metadata.create_all(make_sync_engine(f"sqlite:///{tmp_path / 'w.db'}"))
    cancel.set()
    worker_main(_spec(tmp_path), q, cancel)
    msgs = _drain(q)
    assert [m[0] for m in msgs] == ["event", "record", "done"]
    assert msgs[0][1] == 5
    assert msgs[2] == ("done", 5, {"status": "cancelled", "error": None, "counters": {"linked": 2}})


def test_worker_exception_still_sends_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise KeyError("x")

    monkeypatch.setattr(worker_mod, "run_rip", boom)
    ctx = mp.get_context("spawn")
    q = FakeQ()
    Base.metadata.create_all(make_sync_engine(f"sqlite:///{tmp_path / 'w.db'}"))
    worker_main(_spec(tmp_path), q, ctx.Event())
    done = _drain(q)[-1]
    assert done[2]["status"] == "failed" and done[2]["error"] == "worker error: KeyError"


def test_spec_pickle_round_trip_keeps_secrets(tmp_path: Path) -> None:
    import pickle

    from app.db.models import CredentialKind
    from app.rip.snapshot import CredentialSnapshot

    spec = _spec(tmp_path)
    spec.credential = CredentialSnapshot(
        site="s", kind=CredentialKind(list(CredentialKind)[0]), secret="sek"
    )  # type: ignore[arg-type]
    back = pickle.loads(pickle.dumps(spec))
    assert back.target.api_key.get_secret_value() == "k"
    assert back.credential is not None and back.credential.secret.get_secret_value() == "sek"
    assert back == spec


def test_readonly_engine_with_async_url(tmp_path: Path) -> None:
    import sqlalchemy as sa

    from app.runtime.worker import make_readonly_engine

    url = f"sqlite+aiosqlite:///{tmp_path / 'ro.db'}"
    Base.metadata.create_all(make_sync_engine(url))
    eng = make_readonly_engine(url)
    with eng.connect() as c:
        assert c.execute(sa.text("select count(*) from jobs")).scalar_one() == 0
    with pytest.raises(sa.exc.OperationalError), eng.begin() as c:
        c.execute(sa.text("insert into settings (key, value) values ('k', '{}')"))
