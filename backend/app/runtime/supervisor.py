"""Job supervisor: queue, concurrency rules, worker lifecycle, cancel and recovery."""

import asyncio
import logging
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.crypto import SecretBox
from app.db.models import AssetSeen, Job, JobStatus, Source
from app.rip.build import build_snapshots, check_notify_refs, credential_snapshot
from app.rip.pipeline import sweep_scratch
from app.rip.settings import DEFAULT_SCRATCH_MAX_BYTES, load_rip_settings
from app.runtime.notify import notify_job, shutdown_executor
from app.runtime.settings import load_notify_settings, load_runtime_settings
from app.runtime.worker import WorkerSpec, worker_main
from app.runtime.writer import JobWriter

log = logging.getLogger(__name__)

SWEEP_INTERVAL_S = 600.0
RESTART_ERROR = "interrupted by restart"


class JobConflict(Exception):
    """The source already has a queued or running job (``job_id``, when known)."""

    def __init__(self, source_id: int, job_id: int | None = None) -> None:
        super().__init__(source_id)
        self.source_id = source_id
        self.job_id = job_id


class JobNotActive(Exception):
    """The job is not queued or running."""


@dataclass
class RunHandle:
    target_id: int
    source_id: int
    cancel_event: Any
    started: float = field(default_factory=time.monotonic)
    process: Any = None
    done_result: dict[str, Any] | None = None
    done_evt: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_requested: bool = False
    task: asyncio.Task[None] | None = None
    escalation: asyncio.Task[None] | None = None
    exitcode: int | None = None
    finalized: bool = False


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class JobSupervisor:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer: JobWriter,
        settings: Settings,
        *,
        mp_ctx: Any,
        ipc_queue: Any,
        worker_target: Callable[..., None] = worker_main,
    ) -> None:
        self._sf = session_factory
        self._writer = writer
        self._settings = settings
        self._ctx = mp_ctx
        self._q = ipc_queue
        self._target = worker_target
        self.running: dict[int, RunHandle] = {}
        self.poll_s = 1.0
        self.kill_delay_s = 5.0
        self.done_wait_s = 5.0
        self.stop_join_s = 5.0
        self.grace_override_s: float | None = None
        self._wake = asyncio.Event()
        self._stop = False
        self._loop_task: asyncio.Task[None] | None = None
        self._notify_tasks: set[asyncio.Task[None]] = set()
        self._skip: set[int] = set()  # queued jobs cancelled but not yet committed
        writer.add_done_listener(self._on_done)

    # -- public ----------------------------------------------------------
    @property
    def alive(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    async def start(self) -> None:
        async with self._sf() as s:
            stale = (
                await s.execute(
                    select(Job.id, Job.source_id).where(Job.status == JobStatus.running)
                )
            ).all()
        for job_id, source_id in stale:  # via the writer so metrics and notifications see them
            self._finish(job_id, "failed", RESTART_ERROR, source_id=source_id)
        deadline = time.monotonic() + 10
        while stale and time.monotonic() < deadline:
            async with self._sf() as s:
                left = await s.scalar(
                    select(Job.id)
                    .where(Job.id.in_([j for j, _ in stale]), Job.status == JobStatus.running)
                    .limit(1)
                )
            if left is None:
                break
            await asyncio.sleep(0.05)
        await asyncio.to_thread(sweep_scratch, self._settings.scratch_dir, set())
        self._stop = False
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop = True
        self._wake.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
            self._loop_task = None
        handles = dict(self.running)
        for job_id in handles:
            self._request_cancel(job_id)
        grace = await self._grace()
        tasks = [h.task for h in handles.values() if h.task is not None]
        pending: set[asyncio.Task[None]] = set()
        if tasks:
            _, pending = await asyncio.wait(
                tasks, timeout=grace + self.kill_delay_s + self.stop_join_s
            )
        if pending:
            for h in handles.values():
                if self._signal(h, "kill"):
                    deadline = time.monotonic() + self.stop_join_s
                    while self._alive(h) and time.monotonic() < deadline:
                        await asyncio.sleep(0.02)
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for job_id in handles:
                shutil.rmtree(self._settings.scratch_dir / str(job_id), ignore_errors=True)
        for job_id, h in handles.items():
            if h.escalation is not None:
                h.escalation.cancel()
            if not h.finalized:
                self._finish(job_id, "failed", RESTART_ERROR, source_id=h.source_id)
        shutdown_executor()
        pending_notify = list(self._notify_tasks)
        for nt in pending_notify:
            nt.cancel()
        await asyncio.gather(*pending_notify, return_exceptions=True)

    async def enqueue(self, source_id: int, triggered_by: int | None, log_level: str | None) -> Job:
        async with self._sf() as s, s.begin():
            active = await s.execute(
                select(Job.id)
                .where(
                    Job.source_id == source_id,
                    Job.status.in_((JobStatus.queued, JobStatus.running)),
                )
                .limit(1)
            )
            row = active.first()
            if row is not None:
                raise JobConflict(source_id, row[0])
            job = Job(
                source_id=source_id,
                triggered_by=triggered_by,
                status=JobStatus.queued,
                log_level=log_level,
            )
            s.add(job)
            try:
                await s.flush()
            except IntegrityError:
                await s.rollback()
                raise JobConflict(source_id, await self._active_job_id(source_id)) from None
        self._wake.set()
        return job

    async def _active_job_id(self, source_id: int) -> int | None:
        async with self._sf() as s:
            return await s.scalar(
                select(Job.id)
                .where(
                    Job.source_id == source_id,
                    Job.status.in_((JobStatus.queued, JobStatus.running)),
                )
                .limit(1)
            )

    async def cancel(self, job_id: int) -> None:
        if job_id in self.running:
            self._request_cancel(job_id)
            return
        queued = await self._is_queued(job_id)
        if job_id in self.running:  # picked while we awaited the DB
            self._request_cancel(job_id)
            return
        if not queued or job_id in self._skip:
            raise JobNotActive(job_id)
        self._skip.add(job_id)
        self._writer.submit(("status", job_id, "cancelled", {"finished_at": _now()}))
        self._wake.set()

    async def _is_queued(self, job_id: int) -> bool:
        async with self._sf() as s:
            job = await s.get(Job, job_id)
        return job is not None and job.status == JobStatus.queued

    async def is_incremental(self, source_id: int) -> bool:
        async with self._sf() as s:
            row = await s.execute(
                select(AssetSeen.id).where(AssetSeen.source_id == source_id).limit(1)
            )
            return row.first() is not None

    # -- internals -------------------------------------------------------
    async def _on_done(self, job_id: int, result: dict[str, Any]) -> None:
        h = self.running.get(job_id)
        if h is not None and h.done_result is None:
            h.done_result = result
            h.done_evt.set()
        else:
            log.warning("done for job %s ignored (not running or already finalized)", job_id)

    async def _grace(self) -> float:
        if self.grace_override_s is not None:
            return self.grace_override_s
        async with self._sf() as s:
            return float((await load_runtime_settings(s)).cancel_grace_s)

    def _request_cancel(self, job_id: int) -> None:
        h = self.running.get(job_id)
        if h is None:
            return
        h.cancel_requested = True
        h.cancel_event.set()
        if h.process is not None and h.escalation is None:
            h.escalation = asyncio.create_task(self._escalate(h))
        self._wake.set()

    @staticmethod
    def _alive(h: RunHandle) -> bool:
        proc = h.process
        if proc is None or h.exitcode is not None:
            return False
        try:
            return bool(proc.is_alive())
        except ValueError:  # process object already closed
            return False

    def _signal(self, h: RunHandle, how: str) -> bool:
        """Send terminate/kill when the worker is still alive; True if sent."""
        if not self._alive(h):
            return False
        try:
            getattr(h.process, how)()
        except ValueError:
            return False
        return True

    async def _escalate(self, h: RunHandle) -> None:
        await asyncio.sleep(await self._grace())
        if self._signal(h, "terminate"):
            await asyncio.sleep(self.kill_delay_s)
            self._signal(h, "kill")

    async def _loop(self) -> None:
        last_sweep = time.monotonic()
        while not self._stop:
            self._wake.clear()
            try:
                await self._start_ready()
                if time.monotonic() - last_sweep >= SWEEP_INTERVAL_S:
                    last_sweep = time.monotonic()
                    await asyncio.to_thread(
                        sweep_scratch, self._settings.scratch_dir, set(self.running)
                    )
            except Exception:
                log.exception("supervisor loop error")
            try:
                await asyncio.wait_for(self._wake.wait(), self.poll_s)
            except TimeoutError:
                pass

    async def _start_ready(self) -> None:
        if self._stop:
            return
        async with self._sf() as s:
            runtime = await load_runtime_settings(s)
            cap = runtime.max_concurrent_jobs or os.cpu_count() or 1
            rows = (
                await s.execute(
                    select(Job.id, Job.source_id, Source.target_id)
                    .join(Source, Source.id == Job.source_id)
                    .where(Job.status == JobStatus.queued)
                    .order_by(Job.id)
                )
            ).all()
        self._skip &= {r[0] for r in rows}
        if len(self.running) >= cap:
            return
        busy = {h.target_id for h in self.running.values()}
        for job_id, source_id, target_id in rows:
            if len(self.running) >= cap:
                break
            if job_id in self.running or job_id in self._skip or target_id in busy:
                continue
            h = RunHandle(target_id, source_id, self._ctx.Event())
            self.running[job_id] = h
            busy.add(target_id)
            h.task = asyncio.create_task(self._run_job(job_id, h))

    async def _prepare(self, job_id: int, h: RunHandle) -> WorkerSpec | str:
        """Return the worker spec, or a failure message."""
        async with self._sf() as s:
            job = await s.get(Job, job_id)
            source = await s.get(Source, h.source_id)
            if job is None or source is None:
                return "source missing"
            box = SecretBox(self._settings.master_key_value())
            try:
                source_snap, target_snap, cred = await build_snapshots(s, source, box)
            except HTTPException as e:
                return "access revoked" if e.status_code == 403 else f"cannot start: {e.detail}"
            rip = await load_rip_settings(s)
            incremental = await self.is_incremental(source.id)
            return WorkerSpec(
                job_id=job_id,
                source=source_snap,
                target=target_snap,
                credential=cred,
                rip_settings=rip,
                scratch_dir=self._settings.scratch_dir,
                scratch_cap_bytes=rip.job_scratch_max_bytes or DEFAULT_SCRATCH_MAX_BYTES,
                incremental=incremental,
                db_url=self._settings.database_url,
                log_level=job.log_level or source.log_level or self._settings.log_level,
            )

    def _finish(
        self,
        job_id: int,
        status: str,
        error: str | None,
        counters: Any = None,
        source_id: int | None = None,
    ) -> None:
        h = self.running.get(job_id)
        if h is not None:
            h.finalized = True
        fields: dict[str, Any] = {"error": error, "finished_at": _now()}
        if counters is not None:
            fields["counters"] = counters
        self._writer.submit(("status", job_id, status, fields))
        if source_id is not None:
            task = asyncio.create_task(
                self._notify(job_id, source_id, status, error, dict(counters or {}))
            )
            self._notify_tasks.add(task)
            task.add_done_callback(self._notify_tasks.discard)

    async def _notify(
        self, job_id: int, source_id: int, status: str, error: str | None, counters: dict[str, Any]
    ) -> None:
        """Runs detached, after the final status commits; never raises."""
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                async with self._sf() as s:
                    job = await s.get(Job, job_id)
                if job is not None and job.status == status:
                    break
                await asyncio.sleep(0.1)
            async with self._sf() as s:
                src = await s.get(Source, source_id)
                if src is None:
                    return
                name, cfg = src.name, dict(src.notify or {})
                gl = await load_notify_settings(s)
                box = SecretBox(self._settings.master_key_value())
                src_urls: list[str] = []
                allow_private = (await load_rip_settings(s)).allow_private_hosts
                for cid in cfg.get("credential_ids") or []:
                    try:
                        # re-checks use, kind and SSRF (host may have turned private)
                        await check_notify_refs(s, src.owner_id, {"credential_ids": [cid]}, box)
                        src_urls.append(
                            (await credential_snapshot(s, cid, box)).secret.get_secret_value()
                        )
                    except HTTPException:
                        log.warning("job %s: notification credential %s skipped", job_id, cid)
            if src_urls:
                await notify_job(
                    job_id,
                    name,
                    counters,
                    status,
                    error,
                    src_urls,
                    cfg.get("on") or ["failure"],
                    block_private=not allow_private,
                )
            if gl.urls:
                await notify_job(job_id, name, counters, status, error, gl.urls, gl.on)
        except Exception as e:
            log.warning("job %s: notification setup failed (%s)", job_id, type(e).__name__)

    async def _run_job(self, job_id: int, h: RunHandle) -> None:
        try:
            await self._run_job_inner(job_id, h)
        except Exception as e:
            log.exception("job %s supervision failed", job_id)
            self._finish(
                job_id, "failed", f"supervisor error: {type(e).__name__}", source_id=h.source_id
            )
        finally:
            await asyncio.to_thread(shutil.rmtree, self._settings.scratch_dir / str(job_id), True)
            self.running.pop(job_id, None)
            self._wake.set()

    async def _await_done(self, job_id: int, h: RunHandle) -> None:
        if h.exitcode == 0:  # worker_main always sends done before a clean exit
            while not h.done_evt.is_set():
                try:
                    await asyncio.wait_for(h.done_evt.wait(), 30)
                except TimeoutError:
                    log.warning("job %s: still waiting for done after clean worker exit", job_id)
            return
        try:
            await asyncio.wait_for(h.done_evt.wait(), self.done_wait_s)
        except TimeoutError:
            pass

    async def _run_job_inner(self, job_id: int, h: RunHandle) -> None:
        spec = await self._prepare(job_id, h)
        if isinstance(spec, str):
            self._finish(job_id, "failed", spec, source_id=h.source_id)
            return
        if h.cancel_requested or job_id in self._skip:
            self._finish(job_id, "cancelled", None, source_id=h.source_id)
            return
        self._writer.submit(("status", job_id, "running", {"started_at": _now()}))
        proc = self._ctx.Process(
            target=self._target, args=(spec, self._q, h.cancel_event), daemon=True
        )
        await asyncio.to_thread(proc.start)
        h.process = proc
        if h.cancel_requested and h.escalation is None:
            h.escalation = asyncio.create_task(self._escalate(h))
        while proc.exitcode is None:
            await asyncio.sleep(self.poll_s)
        h.exitcode = proc.exitcode
        proc.join(0)
        proc.close()
        h.process = None
        if h.done_result is None:
            await self._await_done(job_id, h)
        if h.escalation is not None:
            h.escalation.cancel()
        res = h.done_result
        if self._stop:  # shutdown wins over any worker outcome, cancelled included
            self._finish(job_id, "failed", RESTART_ERROR, source_id=h.source_id)
        elif res is not None:
            self._finish(job_id, res["status"], res.get("error"), res.get("counters"), h.source_id)
        elif h.cancel_requested:
            self._finish(job_id, "cancelled", None, source_id=h.source_id)
        else:
            self._finish(job_id, "failed", "worker crashed", source_id=h.source_id)
