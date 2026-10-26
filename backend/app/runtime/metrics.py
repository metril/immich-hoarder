"""Prometheus metrics fed by the event bus (one dedicated registry, no globals)."""

import asyncio
import logging
import shutil
import time
from collections import deque
from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.runtime.bus import EventBus, Subscription

log = logging.getLogger(__name__)

_TERMINAL = {"succeeded", "failed", "cancelled"}
_SEEN_MAX = 4096


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.jobs_total = Counter(
            "ih_jobs_total", "Finished jobs", ["status"], registry=self.registry
        )
        self.items_total = Counter(
            "ih_items_total", "Item outcomes", ["outcome"], registry=self.registry
        )
        self.jobs_running = Gauge("ih_jobs_running", "Running jobs", registry=self.registry)
        self.jobs_queued = Gauge("ih_jobs_queued", "Queued jobs", registry=self.registry)
        self.duration = Histogram(
            "ih_job_duration_seconds",
            "Job run duration",
            buckets=(1, 5, 15, 60, 300, 900, 3600, 14400),
            registry=self.registry,
        )
        self.scratch_bytes = Gauge(
            "ih_scratch_bytes", "Scratch dir used bytes", registry=self.registry
        )
        self._started: dict[int, float] = {}
        self._finished: deque[int] = deque(maxlen=_SEEN_MAX)
        self._finished_set: set[int] = set()
        self._sub: Subscription | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self, bus: EventBus) -> None:
        self._sub = bus.subscribe(None)
        self._task = asyncio.create_task(self._run(self._sub))

    async def stop(self) -> None:
        if self._sub is not None:
            self._sub.close()
            self._sub = None
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def idle(self) -> bool:
        return self._sub is None or self._sub.empty()

    async def _run(self, sub: Subscription) -> None:
        async for ev in sub:
            try:
                self.observe(ev)
            except Exception:
                log.exception("metrics: event handling failed")

    def observe(self, ev: dict[str, object]) -> None:
        typ = str(ev.get("type", ""))
        job_id = ev.get("job_id")
        if typ.startswith("item."):
            self.items_total.labels(typ.removeprefix("item.")).inc()
        elif typ == "status" and isinstance(job_id, int):
            status = str(ev.get("status"))
            if status == "running":
                self._started.setdefault(job_id, time.monotonic())
            elif status in _TERMINAL and job_id not in self._finished_set:
                if len(self._finished) == _SEEN_MAX:
                    self._finished_set.discard(self._finished[0])
                self._finished.append(job_id)
                self._finished_set.add(job_id)
                self.jobs_total.labels(status).inc()
                t0 = self._started.pop(job_id, None)
                if t0 is not None:
                    self.duration.observe(time.monotonic() - t0)

    def set_scratch(self, scratch_dir: Path) -> None:
        try:
            self.scratch_bytes.set(shutil.disk_usage(scratch_dir).used)
        except OSError:
            self.scratch_bytes.set(0)
