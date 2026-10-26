import asyncio
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import Source
from app.runtime.maintenance import backup_sqlite, prune_ephemeral_sources, prune_jobs
from app.runtime.settings import load_runtime_settings
from app.runtime.supervisor import JobConflict, JobSupervisor

log = logging.getLogger(__name__)


class CroniterTrigger(BaseTrigger):  # type: ignore[misc]
    """Cron trigger backed by croniter (Sunday=0, @aliases), evaluated in UTC."""

    def __init__(self, expr: str) -> None:
        if not croniter.is_valid(expr):
            raise ValueError(f"invalid cron expression: {expr!r}")
        self.expr = expr

    def get_next_fire_time(
        self, previous_fire_time: datetime | None, now: datetime
    ) -> datetime | None:
        nxt: datetime = croniter(self.expr, now.astimezone(UTC)).get_next(datetime)
        return nxt.astimezone(UTC)

    def __str__(self) -> str:
        return f"croniter[{self.expr}]"


def _job_id(source_id: int) -> str:
    return f"source-{source_id}"


class SourceScheduler:
    def __init__(
        self,
        supervisor: JobSupervisor,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings
        self._sup = supervisor
        self._sf = session_factory
        self._sched = AsyncIOScheduler(timezone=UTC)

    async def _fire(self, source_id: int) -> None:
        try:
            await self._sup.enqueue(source_id, None, None)
        except JobConflict:
            log.info("scheduled run skipped: source %s already active", source_id)
        except Exception as e:
            log.error("scheduled run failed for source %s: %s", source_id, type(e).__name__)

    @property
    def running(self) -> bool:
        return bool(self._sched.running)

    def job_ids(self) -> set[str]:
        return {j.id for j in self._sched.get_jobs() if j.id.startswith("source-")}

    async def _prune(self) -> None:
        try:
            async with self._sf() as s:
                rt = await load_runtime_settings(s)
                jobs = await prune_jobs(s, rt.retention_days)
                eph = await prune_ephemeral_sources(s)
                await s.commit()
            log.info("pruned %s jobs, %s ephemeral sources", jobs, eph)
        except Exception as e:
            log.error("prune failed: %s", type(e).__name__)

    async def _backup(self) -> None:
        if self._settings is None:
            return
        try:
            async with self._sf() as s:
                keep = (await load_runtime_settings(s)).backup_keep
            if keep == 0:
                return
            await asyncio.to_thread(
                backup_sqlite, self._settings.database_url, self._settings.backup_dir, keep
            )
        except Exception as e:
            log.error("backup failed: %s", type(e).__name__)

    async def sync_maintenance(self) -> None:
        """(Re)register the daily prune and the backup on the configured cron."""
        self._sched.add_job(
            self._prune,
            CroniterTrigger("0 4 * * *"),
            id="maintenance-prune",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        if self._settings is None:
            return
        async with self._sf() as s:
            rt = await load_runtime_settings(s)
        if rt.backup_keep == 0:
            if self._sched.get_job("maintenance-backup") is not None:
                self._sched.remove_job("maintenance-backup")
            return
        cron = rt.backup_cron
        self._sched.add_job(
            self._backup,
            CroniterTrigger(cron),
            id="maintenance-backup",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )

    async def start(self) -> None:
        self._sched.start()
        await self.sync_maintenance()
        async with self._sf() as s:
            ids = (
                await s.scalars(
                    select(Source.id).where(
                        Source.enabled.is_(True),
                        Source.ephemeral.is_(False),
                        Source.schedule_cron.is_not(None),
                    )
                )
            ).all()
        for sid in ids:
            await self.sync_source(sid)

    async def sync_source(self, source_id: int) -> None:
        async with self._sf() as s:
            src = await s.get(Source, source_id)
            cron = src.schedule_cron if src else None
            active = bool(src and src.enabled and not src.ephemeral and cron)
        jid = _job_id(source_id)
        if not active or cron is None:
            if self._sched.get_job(jid) is not None:
                self._sched.remove_job(jid)
            return
        try:
            trigger = CroniterTrigger(cron)
        except ValueError:
            if self._sched.get_job(jid) is not None:
                self._sched.remove_job(jid)
            log.error("invalid cron %r for source %s; unscheduled", cron, source_id)
            return
        # Runs missed across a restart are dropped (memory jobstore, no catch-up).
        self._sched.add_job(
            self._fire,
            trigger,
            args=[source_id],
            id=jid,
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )

    def shutdown(self, wait: bool = False) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=wait)
