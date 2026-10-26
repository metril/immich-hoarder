"""Rip pipeline: gallery-dl download -> analyze -> filter -> dedupe -> Immich upload/link."""

import contextlib
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from app.db.models import BackfillMode
from app.immich.client import ImmichClient
from app.immich.errors import AssetGone, ImmichAuthError, ImmichError, ImmichUnavailable
from app.rip.albums import AlbumResolver, render_album
from app.rip.dedupe import DedupeStore, Recorder
from app.rip.events import Emit
from app.rip.filters import check
from app.rip.gdl import HoarderJob, capture_logs, configure, run_job
from app.rip.media import MediaInfo, NotAnImage, analyze
from app.rip.settings import RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot, TargetSnapshot

_DESC_MAX = 2000
_MIN_FREE_RATIO = 0.05
_COUNTERS = (
    "discovered",
    "downloaded",
    "filtered",
    "duplicate",
    "linked",
    "uploaded",
    "failed",
    "deleted_in_immich",
)
_GONE_ERRORS = frozenset({"not_found", "no_permission"})


@dataclass
class RipContext:
    job_id: int
    source: SourceSnapshot
    target: TargetSnapshot
    credential: CredentialSnapshot | None
    settings: RipSettings
    scratch_dir: Path
    scratch_cap_bytes: int
    incremental: bool
    store: DedupeStore
    recorder: Recorder
    client_factory: Callable[[TargetSnapshot], ImmichClient]


@dataclass
class RipResult:
    counters: dict[str, int]
    status: Literal["succeeded", "failed", "cancelled"]
    error: str | None


def sweep_scratch(scratch_dir: Path, active_job_ids: set[int]) -> int:
    """Remove job dirs (numeric names) that no active job owns; return how many."""
    n = 0
    if not scratch_dir.is_dir():
        return 0
    for p in scratch_dir.iterdir():
        if p.is_dir() and p.name.isdigit() and int(p.name) not in active_job_ids:
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n


def build_description(meta: dict[str, Any]) -> str:
    parts: list[str] = []
    title = meta.get("title")
    if title:
        parts.append(str(title))
    link = meta.get("permalink")
    if link:
        link = str(link)
        parts.append("https://www.reddit.com" + link if link.startswith("/") else link)
    elif meta.get("url"):
        parts.append(str(meta["url"]))
    if meta.get("author"):
        parts.append(f"by {meta['author']}")
    return "\n".join(parts)[:_DESC_MAX]


class _Outcome(Exception):
    """Internal control flow: a terminal non-success outcome for the current item."""

    def __init__(self, kind: str, reason: str | None = None, asset_id: str | None = None):
        super().__init__(kind)
        self.kind = kind
        self.reason = reason
        self.asset_id = asset_id


class _Rip:
    def __init__(self, ctx: RipContext, emit: Emit, cancel: threading.Event) -> None:
        self.ctx = ctx
        self._emit_fn = emit
        self.cancel = cancel
        self.src = ctx.source
        self.counters = dict.fromkeys(_COUNTERS, 0)
        self.bytes = 0
        self.inflight = 0
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.emit_lock = threading.Lock()
        self.sha_lock = threading.Lock()
        self.sha_events: dict[bytes, threading.Event] = {}
        self.fatal: str | None = None
        self.job_dir = ctx.scratch_dir / str(ctx.job_id)
        self.started = time.monotonic()
        self.since: date | None = None
        if not ctx.incremental and self.src.backfill_mode == BackfillMode.since:
            if self.src.backfill_value:
                self.since = date.fromisoformat(self.src.backfill_value)
        self.client: ImmichClient
        self.albums: AlbumResolver

    # -- helpers ---------------------------------------------------------
    def emit(self, ev: dict[str, Any]) -> None:
        with self.emit_lock:
            self._emit_fn(ev)

    def bump(self, name: str, n: int = 1) -> None:
        with self.lock:
            self.counters[name] += n

    def log_error(self, msg: str) -> None:
        self.emit({"type": "log", "level": "error", "msg": msg, "logger": "pipeline"})

    def progress(self) -> None:
        try:
            du = shutil.disk_usage(self.ctx.scratch_dir)
            ratio = du.free / du.total if du.total else 1.0
        except OSError:
            ratio = 1.0
        with self.lock:
            counters = dict(self.counters)
            b, scratch = self.bytes, self.inflight
        el = max(time.monotonic() - self.started, 1e-6)
        self.emit(
            {
                "type": "progress",
                "counters": counters,
                "bytes": b,
                "rate_bps": b / el,
                "scratch_bytes": scratch,
                "scratch_free_ratio": ratio,
            }
        )

    def _disk_low(self) -> bool:
        try:
            du = shutil.disk_usage(self.ctx.scratch_dir)
        except OSError:
            return False
        return du.total > 0 and du.free / du.total < _MIN_FREE_RATIO

    # -- gallery-dl callbacks (calling thread) ---------------------------
    def on_discovered(self, kw: dict[str, Any]) -> None:
        self.bump("discovered")
        self.emit({"type": "item.discovered", "url": self._url(kw, None)})

    @staticmethod
    def _url(meta: dict[str, Any], path: Path | None) -> str:
        v = meta.get("url") or meta.get("_url") or meta.get("permalink")
        if v:
            return str(v)
        if path is not None:
            return path.name
        return str(meta.get("filename") or "")

    def on_file(self, path: Path, meta: dict[str, Any]) -> None:
        try:
            size = path.stat().st_size
        except OSError:
            return
        with self.cond:
            while not self.cancel.is_set() and self.inflight > 0:
                if self.inflight > self.ctx.scratch_cap_bytes or self._disk_low():
                    self.cond.wait(0.5)
                else:
                    break
            if self.cancel.is_set():
                cancelled = True
            else:
                cancelled = False
                self.inflight += size
                self.bytes += size
                self.counters["downloaded"] += 1
        if cancelled:
            self._unlink(path)
            return
        self.pool.submit(self.item, path, meta, size)

    @staticmethod
    def _unlink(path: Path) -> None:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)

    # -- per-item (pool threads) -----------------------------------------
    def item(self, path: Path, meta: dict[str, Any], size: int) -> None:
        url = self._url(meta, path)
        key: bytes = meta["_key"]
        try:
            if self.cancel.is_set():
                return
            self.emit({"type": "item.downloaded", "url": url, "size": size})
            self._process(path, meta, url, key)
        except _Outcome as o:
            self._fail(url, o.kind, o.reason or o.kind)
        except ImmichAuthError:
            self._fatal(url)
        except ImmichUnavailable:
            self._fail(url, "failed", "immich_unavailable")
        except ImmichError:
            self._fail(url, "failed", "immich_error")
        except Exception as e:
            self.log_error(f"internal error processing item: {type(e).__name__}: {e}")
            self._fail(url, "failed", "internal_error")
        finally:
            self._unlink(path)
            with self.cond:
                self.inflight -= size
                self.cond.notify_all()

    def _fatal(self, url: str) -> None:
        self.fatal = "immich unauthorized"
        self.cancel.set()
        self._fail(url, "failed", "immich_unauthorized")

    def _fail(self, url: str, _kind: str, reason: str) -> None:
        self.bump("failed")
        self.emit({"type": "item.failed", "url": url, "reason": reason})

    def _record(
        self, key: bytes, sha1: bytes | None, phash: int | None, asset_id: str | None
    ) -> None:
        self.ctx.recorder.record(
            target_id=self.ctx.target.id,
            source_id=self.src.id,
            key=key,
            sha1=sha1,
            phash=phash,
            immich_asset_id=asset_id,
        )

    def _process(self, path: Path, meta: dict[str, Any], url: str, key: bytes) -> None:
        try:
            info = analyze(path)
        except NotAnImage:
            self._filtered(url, key, "not_an_image")
            return
        reason = check(info, meta, self.src.filters, self.src.allow_animated, since=self.since)
        if reason is not None:
            self._filtered(url, key, reason)
            return
        owned = self._acquire(info.sha1)
        try:
            self._dedupe_and_upload(path, meta, url, key, info)
        finally:
            if owned is not None:
                with self.sha_lock:
                    self.sha_events.pop(info.sha1, None)
                owned.set()

    def _acquire(self, sha1: bytes) -> threading.Event | None:
        while True:
            with self.sha_lock:
                ev = self.sha_events.get(sha1)
                if ev is None:
                    mine = threading.Event()
                    self.sha_events[sha1] = mine
                    return mine
            ev.wait()

    def _filtered(self, url: str, key: bytes, reason: str) -> None:
        self._record(key, None, None, None)
        self.bump("filtered")
        self.emit({"type": "item.filtered", "url": url, "reason": reason})

    def _dedupe_and_upload(
        self, path: Path, meta: dict[str, Any], url: str, key: bytes, info: MediaInfo
    ) -> None:
        ctx = self.ctx
        tid = ctx.target.id
        existing: str | None = None
        how = ""
        ref = ctx.store.match_sha1(tid, info.sha1)
        if ref is not None:
            how = "sha1"
        elif self.src.filters.phash_distance is not None:
            ref = ctx.store.match_phash(tid, info.phash, self.src.filters.phash_distance)
            how = "phash"
        if ref is not None and ref.immich_asset_id:
            existing = ref.immich_asset_id
        else:
            sha1hex = info.sha1.hex()
            res = self.client.bulk_check([("x", sha1hex)]).get("x")
            if res is not None and res.action == "reject" and res.reason == "duplicate":
                if res.is_trashed:
                    self._record(key, info.sha1, info.phash, None)
                    self.bump("deleted_in_immich")
                    self.emit({"type": "item.deleted_in_immich", "url": url})
                    return
                existing, how = res.asset_id, "immich"
        fresh = False
        if existing is None:
            created = meta.get("date")
            if not isinstance(created, datetime):
                created = datetime.now(UTC)
            did = f"{meta.get('category')}-{meta.get('id', key.hex())}-{meta.get('num', 0)}"
            up = self.client.upload(
                path,
                sha1hex=info.sha1.hex(),
                device_asset_id=did,
                file_created_at=created,
                file_modified_at=created,
                filename=path.name,
            )
            asset_id = up.asset_id
            if up.duplicate:
                how = "upload"
            else:
                fresh = True
        else:
            asset_id = existing
        if not fresh:
            self.bump("duplicate")
            self.emit(
                {
                    "type": "item.duplicate",
                    "url": url,
                    "reason": how,
                    "immich_asset_id": asset_id,
                }
            )
        outcome = self._link(asset_id, meta)
        if outcome == "gone":
            self._record(key, info.sha1, info.phash, None)
            self.bump("deleted_in_immich")
            self.emit({"type": "item.deleted_in_immich", "url": url, "immich_asset_id": asset_id})
            return
        if outcome == "failed":
            self._fail(url, "failed", "link_failed")
            return
        if fresh:
            self._describe(asset_id, meta)
        self._record(key, info.sha1, info.phash, asset_id)
        if fresh:
            self.bump("uploaded")
            self.emit({"type": "item.uploaded", "url": url, "immich_asset_id": asset_id})
        else:
            self.bump("linked")
            self.emit({"type": "item.linked", "url": url, "immich_asset_id": asset_id})

    def _link(self, asset_id: str, meta: dict[str, Any]) -> Literal["ok", "gone", "failed"]:
        name = render_album(self.src.album_template, meta, self.src.name)
        res = self.client.add_to_album(self.albums.resolve(name), [asset_id])
        err = res.get(asset_id)
        if err is None:
            return "ok"
        if err in _GONE_ERRORS:
            try:
                info = self.client.get_asset(asset_id)
            except AssetGone:
                return "gone"
            return "gone" if info.is_trashed else "failed"
        return "failed"

    def _describe(self, asset_id: str, meta: dict[str, Any]) -> None:
        d = meta.get("date")
        try:
            self.client.update_asset(
                asset_id,
                description=build_description(meta) or None,
                date_time_original=d if isinstance(d, datetime) else None,
            )
        except ImmichAuthError:
            raise
        except (ImmichError, ImmichUnavailable) as e:
            self.log_error(f"could not describe asset: {type(e).__name__}")

    # -- orchestration ---------------------------------------------------
    def run(self) -> RipResult:
        ctx = self.ctx
        self.emit({"type": "phase", "name": "starting"})
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.client = ctx.client_factory(ctx.target)
        self.albums = AlbumResolver(self.client)
        self.pool = ThreadPoolExecutor(ctx.settings.upload_concurrency)
        stop_tick = threading.Event()

        def tick() -> None:
            while not stop_tick.wait(2.0):
                self.progress()

        ticker = threading.Thread(target=tick, daemon=True)
        ticker.start()
        gdl_status = 0
        error: str | None = None
        try:
            configure(self.src, ctx.credential, ctx.settings, self.job_dir, ctx.incremental)
            job = HoarderJob(
                self.src.url,
                archive_check=lambda k: ctx.store.url_seen(self.src.id, k),
                on_discovered=self.on_discovered,
                on_file=self.on_file,
                cancel=self.cancel,
            )
            self.emit({"type": "phase", "name": "extracting"})
            with capture_logs(self.emit, self.src.log_level, categories=(self.src.extractor,)):
                gdl_status = run_job(job, self.src, ctx.settings)
        except Exception as e:
            self.log_error(f"extraction crashed: {type(e).__name__}: {e}")
            error = "internal error"
        finally:
            self.emit({"type": "phase", "name": "draining"})
            self.pool.shutdown(wait=True)
            stop_tick.set()
            ticker.join()
            self.progress()
            shutil.rmtree(self.job_dir, ignore_errors=True)
            with contextlib.suppress(Exception):
                self.client.close()
        if self.fatal:
            status: Literal["succeeded", "failed", "cancelled"] = "failed"
            error = self.fatal
        elif self.cancel.is_set():
            status = "cancelled"
        else:
            ok = sum(v for k, v in self.counters.items() if k not in ("failed", "discovered"))
            if error is None and gdl_status != 0 and ok == 0:
                error = f"gallery-dl exited with status {gdl_status}"
            status = "failed" if error else "succeeded"
        self.emit({"type": "phase", "name": "done"})
        return RipResult(counters=dict(self.counters), status=status, error=error)


def run_rip(ctx: RipContext, emit: Emit, cancel: threading.Event) -> RipResult:
    return _Rip(ctx, emit, cancel).run()


__all__ = ["RipContext", "RipResult", "build_description", "run_rip", "sweep_scratch"]
