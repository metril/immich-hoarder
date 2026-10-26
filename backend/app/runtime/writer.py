"""Batched DB writer: the parent is the only writer of job data and assets_seen."""

import asyncio
import contextlib
import logging
import queue
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AssetSeen, Job, JobEvent, JobItem, JobStatus
from app.rip.dedupe import assets_seen_row, insert_ignore
from app.runtime.bus import EventBus

log = logging.getLogger(__name__)

FLUSH_INTERVAL = 0.25
BATCH_MAX = 500
URL_MAX = 2048
REASON_MAX = 1000
IPC_QUEUE_MAX = 10000
STOP_TIMEOUT = 10.0
RESTART_MIN_INTERVAL = 1.0

Msg = tuple[Any, ...]
DoneListener = Callable[[int, dict[str, Any]], Awaitable[None]]


_LEVEL_ALIASES = {"warning": "warn", "critical": "error", "fatal": "error"}
_LEVELS = frozenset({"trace", "debug", "info", "warn", "error"})


def _norm_level(level: object) -> str:
    lv = str(level or "info").lower()
    lv = _LEVEL_ALIASES.get(lv, lv)
    return lv if lv in _LEVELS else "info"


class JobWriter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], bus: EventBus) -> None:
        self._sf = session_factory
        self._bus = bus
        self._queue: asyncio.Queue[Msg | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._stopped = False
        self._last_restart = float("-inf")
        self._hook: Callable[[], None] | None = None  # test fault-injection point
        self._respawn_timer: asyncio.TimerHandle | None = None
        self._done_listeners: list[DoneListener] = []
        self._observers: list[Callable[[Msg], None]] = []

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    def add_observer(self, fn: Callable[[Msg], None]) -> None:
        """Call ``fn(msg)`` for every message after its batch commits (lossless, sync)."""
        self._observers.append(fn)

    def add_done_listener(self, cb: DoneListener) -> None:
        """Call ``cb(job_id, result)`` after the batch carrying a "done" message commits."""
        self._done_listeners.append(cb)

    def _cancel_timer(self) -> None:
        if self._respawn_timer is not None:
            self._respawn_timer.cancel()
            self._respawn_timer = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._cancel_timer()
        self._stopping = self._stopped = False
        self._drop_sentinels()
        self._spawn()

    def _drop_sentinels(self) -> None:
        keep: list[Msg] = []
        while not self._queue.empty():
            m = self._queue.get_nowait()
            if m is not None:
                keep.append(m)
        for m in keep:
            self._queue.put_nowait(m)

    def _spawn(self) -> None:
        self._task = asyncio.create_task(self._run())
        self._task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[None]) -> None:
        if self._stopping or task.cancelled():
            return
        exc = task.exception()
        loop = asyncio.get_running_loop()
        delay = max(0.0, self._last_restart + RESTART_MIN_INTERVAL - loop.time())
        log.error("writer task exited unexpectedly; restarting in %.2fs", delay, exc_info=exc)
        self._respawn_timer = loop.call_later(delay, self._respawn)

    def _respawn(self) -> None:
        self._respawn_timer = None
        if self._stopping:
            return
        self._last_restart = asyncio.get_running_loop().time()
        self._spawn()

    def submit(self, msg: Msg) -> None:
        if self._stopped:
            log.warning("writer: message submitted after stop; dropped")
            return
        self._queue.put_nowait(msg)

    async def stop(self, timeout: float = STOP_TIMEOUT) -> None:
        self._stopping = True
        self._cancel_timer()
        self._queue.put_nowait(None)
        task, self._task = self._task, None
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout)
            except TimeoutError:
                log.error("writer did not drain within %ss; cancelled", timeout)
            except Exception:
                log.exception("writer task had already failed")
        self._stopped = True

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        done = False
        while not done:
            if self._hook is not None:
                self._hook()
            first = await self._queue.get()
            if first is None:
                return
            batch: list[Msg] = [first]
            deadline = loop.time() + FLUSH_INTERVAL
            while len(batch) < BATCH_MAX:
                try:
                    nxt = await asyncio.wait_for(
                        self._queue.get(), max(0.0, deadline - loop.time())
                    )
                except TimeoutError:
                    break
                if nxt is None:
                    done = True
                    break
                batch.append(nxt)
            await self._flush(batch)

    async def _commit(self, msgs: list[Msg]) -> None:
        async with self._sf() as session, session.begin():
            await self._apply(session, msgs)

    async def _flush(self, batch: list[Msg]) -> None:
        valid: list[Msg] = []
        for msg in batch:
            err = _validate(msg)
            if err is None:
                valid.append(msg)
            else:
                log.error("writer: malformed message dropped (%s)", err)
        if not valid:
            return
        ok: list[Msg] = []
        try:
            await self._commit(valid)
            ok = valid
        except Exception:
            log.exception("writer batch failed; retrying %d messages individually", len(valid))
            for msg in valid:
                try:
                    await self._commit([msg])
                    ok.append(msg)
                except Exception:
                    log.exception("writer: message dropped (%s)", msg[0])
        for msg in ok:
            for obs in tuple(self._observers):
                try:
                    obs(msg)
                except Exception:
                    log.exception("writer: observer failed")
            try:
                if msg[0] == "event":
                    self._bus.publish(msg[1], msg[2])
                elif msg[0] == "status":
                    self._bus.publish(
                        msg[1], {"type": "status", "job_id": msg[1], "status": msg[2]}
                    )
            except Exception:
                log.exception("writer: publish failed")
        for msg in ok:
            if msg[0] == "done":
                for cb in tuple(self._done_listeners):
                    try:
                        await cb(msg[1], msg[2])
                    except Exception:
                        log.exception("writer: done listener failed")

    async def _apply(self, session: AsyncSession, batch: list[Msg]) -> None:
        counters: dict[int, dict[str, Any]] = {}
        statuses: list[Msg] = []
        dialect = session.get_bind().dialect.name
        for msg in batch:
            kind = msg[0]
            if kind == "event":
                _, job_id, ev = msg
                typ = ev["type"]
                if typ.startswith("item."):
                    outcome = typ.removeprefix("item.")
                    reason = ev.get("reason")
                    session.add(
                        JobItem(
                            job_id=job_id,
                            url=str(ev.get("url", ""))[:URL_MAX],
                            outcome=outcome,
                            reason=None if reason is None else str(reason)[:REASON_MAX],
                            immich_asset_id=_canon_id(ev.get("immich_asset_id")),
                        )
                    )
                elif typ in ("log", "phase"):
                    level = _norm_level(ev.get("level"))
                    session.add(JobEvent(job_id=job_id, level=level, type=typ, data=ev))
                elif typ == "progress":
                    counters[job_id] = ev["counters"]
            elif kind == "record":
                row = assets_seen_row(**msg[1])
                await session.execute(insert_ignore(dialect, AssetSeen).values(row))
            elif kind == "status":
                statuses.append(msg)
        await session.flush()
        for job_id, c in counters.items():
            await session.execute(update(Job).where(Job.id == job_id).values(counters=c))
        for _, job_id, status, fields in statuses:
            vals = {k: v for k, v in fields.items() if k in _STATUS_FIELDS}
            await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.notin_(_TERMINAL))
                .values(status=JobStatus(status), **vals)
            )


def _canon_id(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return str(uuid.UUID(str(v)))
    except ValueError:
        return str(v)[:64]


_TERMINAL = (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled)
_STATUS_FIELDS = {"error", "started_at", "finished_at", "counters"}
_RECORD_KEYS = {"target_id", "source_id", "key", "sha1", "phash", "immich_asset_id"}


def _validate(msg: Any) -> str | None:
    """Return a reason when the message is malformed, else None."""
    try:
        kind = msg[0]
        if kind == "event":
            _, job_id, ev = msg
            if not isinstance(job_id, int) or not isinstance(ev, dict):
                return "bad event"
            if not isinstance(ev.get("type"), str):
                return "event without type"
            if ev["type"] == "progress" and not isinstance(ev.get("counters"), dict):
                return "progress without counters"
        elif kind == "record":
            if not isinstance(msg[1], dict) or set(msg[1]) != _RECORD_KEYS:
                return "bad record"
            assets_seen_row(**msg[1])
        elif kind == "status":
            _, job_id, status, fields = msg
            if not isinstance(job_id, int) or not isinstance(fields, dict):
                return "bad status"
            JobStatus(status)
        elif kind == "done":
            _, job_id, result = msg
            if not isinstance(job_id, int) or not isinstance(result, dict):
                return "bad done"
            if result.get("status") not in ("succeeded", "failed", "cancelled"):
                return "bad done status"
        else:
            return "unknown kind"
    except (ValueError, TypeError, IndexError, KeyError) as e:
        return type(e).__name__
    return None


class IpcBridge:
    """Daemon thread forwarding worker messages from a multiprocessing queue to the writer."""

    def __init__(self, mp_queue: Any, writer: JobWriter, loop: asyncio.AbstractEventLoop) -> None:
        self._q = mp_queue
        self._writer = writer
        self._loop = loop
        self._halt = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ipc-bridge", daemon=True)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while True:
            try:
                msg = self._q.get()
            except Exception:
                if self._halt.is_set():
                    return
                log.exception("ipc bridge: queue read failed")
                time.sleep(0.05)
                continue
            if msg is None:
                return
            with contextlib.suppress(RuntimeError):  # loop closed during shutdown
                self._loop.call_soon_threadsafe(self._writer.submit, msg)

    def stop(self) -> None:
        """Drain everything queued before the sentinel, then exit."""
        try:
            self._q.put(None, timeout=1)
        except queue.Full:
            log.error("ipc bridge: stop sentinel not queued (queue full)")
        except Exception:
            log.exception("ipc bridge: stop sentinel failed")
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            self._halt.set()


def make_ipc_queue(ctx: Any) -> Any:
    """Bounded worker->parent queue; a full queue back-pressures the workers."""
    return ctx.Queue(maxsize=IPC_QUEUE_MAX)
