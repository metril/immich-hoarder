import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Source
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
        self, supervisor: JobSupervisor, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
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
        return {j.id for j in self._sched.get_jobs()}

    async def start(self) -> None:
        self._sched.start()
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
