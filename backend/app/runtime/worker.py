"""Rip worker process: runs one job, streams events and records to the parent over IPC."""

import logging
import sys
import threading
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import Engine, event

from app.db.engine import make_sync_engine
from app.immich.client import ImmichClient
from app.rip.dedupe import AssetRef, DedupeStore
from app.rip.media import to_signed64
from app.rip.pipeline import RipContext, RipResult, run_rip
from app.rip.settings import RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot, TargetSnapshot

_MASK64 = (1 << 64) - 1
_CANCEL_POLL_S = 0.5


class WorkerSpec(BaseModel):
    job_id: int
    source: SourceSnapshot
    target: TargetSnapshot
    credential: CredentialSnapshot | None
    rip_settings: RipSettings
    scratch_dir: Path
    scratch_cap_bytes: int
    incremental: bool
    db_url: str
    log_level: str


def make_readonly_engine(url: str) -> Engine:
    """Sync engine that rejects writes (the parent is the only DB writer)."""
    engine = make_sync_engine(url)

    def _ro(dbapi_conn: Any, _rec: Any) -> None:
        cur = dbapi_conn.cursor()
        if engine.dialect.name == "sqlite":
            cur.execute("PRAGMA query_only=1")
        else:
            cur.execute("SET default_transaction_read_only = on")
        cur.close()
        if engine.dialect.name != "sqlite":
            dbapi_conn.commit()

    event.listen(engine, "connect", _ro)
    return engine


def _ham(a: int, b: int) -> int:
    return ((a ^ b) & _MASK64).bit_count()


class OverlayStore:
    """Read-only DB store plus an in-memory overlay of this job's own records.

    The worker never writes the DB; records are forwarded to the parent over IPC and
    mirrored in the overlay so later lookups in the same run see them immediately.
    """

    def __init__(self, store: DedupeStore, q: Any, job_id: int) -> None:
        self._store = store
        self._q = q
        self._job_id = job_id
        self._lock = threading.Lock()
        self._keys: set[tuple[int, bytes]] = set()
        self._sha1: dict[tuple[int, bytes], str | None] = {}
        self._phash: list[tuple[int, int, str | None]] = []  # (target, signed phash, asset)

    def url_seen(self, source_id: int, key: bytes) -> bool:
        with self._lock:
            if (source_id, key) in self._keys:
                return True
        return self._store.url_seen(source_id, key)

    def match_sha1(self, target_id: int, sha1: bytes) -> AssetRef | None:
        with self._lock:
            aid = self._sha1.get((target_id, sha1))
        if aid is not None:
            return AssetRef(aid)
        return self._store.match_sha1(target_id, sha1)

    def _phash_hit(self, target_id: int, ph: int, dist: int, deleted: bool) -> AssetRef | None:
        best: tuple[int, str | None] | None = None
        with self._lock:
            for t, p, aid in self._phash:
                if t != target_id or (aid is None) != deleted:
                    continue
                d = _ham(p, ph)
                if d <= dist and (best is None or d < best[0]):
                    best = (d, aid)
        return AssetRef(best[1]) if best else None

    def match_phash(self, target_id: int, phash_signed: int, max_distance: int) -> AssetRef | None:
        hit = self._phash_hit(target_id, phash_signed, max_distance, False)
        return hit or self._store.match_phash(target_id, phash_signed, max_distance)

    def match_deleted(
        self, target_id: int, sha1: bytes, phash_signed: int | None, max_distance: int | None
    ) -> bool:
        with self._lock:
            if (target_id, sha1) in self._sha1 and self._sha1[(target_id, sha1)] is None:
                return True
        if (
            phash_signed is not None
            and max_distance is not None
            and self._phash_hit(target_id, phash_signed, max_distance, True)
        ):
            return True
        return self._store.match_deleted(target_id, sha1, phash_signed, max_distance)

    def record(
        self,
        *,
        target_id: int,
        source_id: int,
        key: bytes,
        sha1: bytes | None,
        phash: int | None,
        immich_asset_id: str | None,
    ) -> None:
        with self._lock:
            self._keys.add((source_id, key))
            if sha1 is not None and (
                immich_asset_id is not None or (target_id, sha1) not in self._sha1
            ):
                self._sha1[(target_id, sha1)] = immich_asset_id
            if phash is not None:
                self._phash.append((target_id, to_signed64(phash), immich_asset_id))
        self._q.put(
            (
                "record",
                {
                    "target_id": target_id,
                    "source_id": source_id,
                    "key": key,
                    "sha1": sha1,
                    "phash": phash,
                    "immich_asset_id": immich_asset_id,
                },
            )
        )


def _result(r: RipResult) -> dict[str, Any]:
    return {"status": r.status, "error": r.error, "counters": r.counters}


def _bridge_cancel(mp_cancel: Any, stop: threading.Event) -> threading.Event:
    flag = threading.Event()

    def watch() -> None:
        while not stop.is_set():
            if mp_cancel.wait(_CANCEL_POLL_S):
                flag.set()
                return

    threading.Thread(target=watch, name="cancel-watch", daemon=True).start()
    return flag


def worker_main(spec: WorkerSpec, q: Any, cancel: Any) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, spec.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop = threading.Event()
    result: dict[str, Any] = {"status": "failed", "error": "worker error", "counters": {}}
    engine = None
    try:
        flag = _bridge_cancel(cancel, stop)
        engine = make_readonly_engine(spec.db_url)
        overlay = OverlayStore(DedupeStore(engine), q, spec.job_id)
        ctx = RipContext(
            job_id=spec.job_id,
            source=spec.source,
            target=spec.target,
            credential=spec.credential,
            settings=spec.rip_settings,
            scratch_dir=spec.scratch_dir,
            scratch_cap_bytes=spec.scratch_cap_bytes,
            incremental=spec.incremental,
            store=cast(DedupeStore, overlay),
            recorder=overlay,
            client_factory=lambda t: ImmichClient(t.url, t.api_key.get_secret_value()),
        )
        res = run_rip(ctx, lambda ev: q.put(("event", spec.job_id, ev)), flag)
        result = _result(res)
    except Exception as e:
        logging.getLogger(__name__).exception("worker failed")
        result = {"status": "failed", "error": f"worker error: {type(e).__name__}", "counters": {}}
    finally:
        stop.set()
        if engine is not None:
            engine.dispose()
        q.put(("done", spec.job_id, result))
        q.close()
        q.join_thread()
