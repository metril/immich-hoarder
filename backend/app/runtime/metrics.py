"""Prometheus metrics fed by the event bus (one dedicated registry, no globals)."""

import shutil
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.runtime.writer import JobWriter

_TERMINAL = {"succeeded", "failed", "cancelled"}
_SEEN_MAX = 4096
OUTCOMES = frozenset(
    {"discovered", "downloaded", "filtered", "linked", "uploaded", "failed", "deleted_in_immich"}
)


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
        self._started: dict[int, datetime] = {}
        self._finished: deque[int] = deque(maxlen=_SEEN_MAX)
        self._finished_set: set[int] = set()

    def attach(self, writer: JobWriter) -> None:
        writer.add_observer(self.observe)

    def observe(self, msg: Any) -> None:
        kind = msg[0]
        if kind == "event":
            typ = str(msg[2].get("type", ""))
            if typ.startswith("item."):
                outcome = typ.removeprefix("item.")
                self.items_total.labels(outcome if outcome in OUTCOMES else "other").inc()
        elif kind == "status":
            _, job_id, status, fields = msg
            if status == "running":
                if fields.get("started_at") is not None:
                    self._started[job_id] = fields["started_at"]
            elif status in _TERMINAL and job_id not in self._finished_set:
                if len(self._finished) == _SEEN_MAX:
                    self._finished_set.discard(self._finished[0])
                self._finished.append(job_id)
                self._finished_set.add(job_id)
                self.jobs_total.labels(status).inc()
                t0 = self._started.pop(job_id, None) or fields.get("started_at")
                t1 = fields.get("finished_at")
                if t0 is not None and t1 is not None:
                    self.duration.observe(max(0.0, (t1 - t0).total_seconds()))

    def set_scratch(self, scratch_dir: Path) -> None:
        try:
            self.scratch_bytes.set(shutil.disk_usage(scratch_dir).used)
        except OSError:
            self.scratch_bytes.set(0)
