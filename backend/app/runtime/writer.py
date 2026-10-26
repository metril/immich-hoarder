"""Batched DB writer: the parent is the only writer of job data and assets_seen."""

import asyncio
import contextlib
import logging
import threading
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

Msg = tuple[Any, ...]


class JobWriter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], bus: EventBus) -> None:
        self._sf = session_factory
        self._bus = bus
        self._queue: asyncio.Queue[Msg | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def submit(self, msg: Msg) -> None:
        self._queue.put_nowait(msg)

    async def stop(self) -> None:
        self._queue.put_nowait(None)
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        done = False
        while not done:
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

    async def _flush(self, batch: list[Msg]) -> None:
        try:
            async with self._sf() as session, session.begin():
                await self._apply(session, batch)
        except Exception:
            log.exception("writer batch failed; dropping %d messages", len(batch))
            return
        for msg in batch:
            if msg[0] == "event":
                self._bus.publish(msg[1], msg[2])
            elif msg[0] == "status":
                self._bus.publish(msg[1], {"type": "status", "job_id": msg[1], "status": msg[2]})

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
                            immich_asset_id=ev.get("immich_asset_id"),
                        )
                    )
                elif typ in ("log", "phase"):
                    level = ev["level"] if typ == "log" else "info"
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
                update(Job).where(Job.id == job_id).values(status=JobStatus(status), **vals)
            )


_STATUS_FIELDS = {"error", "started_at", "finished_at", "counters"}


class IpcBridge:
    """Daemon thread forwarding worker messages from a multiprocessing queue to the writer."""

    def __init__(self, mp_queue: Any, writer: JobWriter, loop: asyncio.AbstractEventLoop) -> None:
        self._q = mp_queue
        self._writer = writer
        self._loop = loop
        self._thread = threading.Thread(target=self._run, name="ipc-bridge", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while True:
            msg = self._q.get()
            if msg is None:
                return
            with contextlib.suppress(RuntimeError):  # loop closed during shutdown
                self._loop.call_soon_threadsafe(self._writer.submit, msg)

    def stop(self) -> None:
        self._q.put(None)
        self._thread.join()
