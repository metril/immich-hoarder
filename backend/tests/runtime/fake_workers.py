"""Module-level spawn targets for supervisor tests (spawn needs importable functions)."""

import os
import signal
import time
from pathlib import Path
from typing import Any


def _done(q: Any, spec: Any, status: str, error: str | None = None) -> None:
    q.put(("done", spec.job_id, {"status": status, "error": error, "counters": {"linked": 1}}))
    q.close()
    q.join_thread()


def _touch(spec: Any) -> None:
    d = Path(spec.scratch_dir) / str(spec.job_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "f").write_text("x")


def fast_worker(spec: Any, q: Any, cancel: Any) -> None:
    _touch(spec)
    q.put(("event", spec.job_id, {"type": "phase", "name": "starting"}))
    _done(q, spec, "succeeded")


def failing_worker(spec: Any, q: Any, cancel: Any) -> None:
    _touch(spec)
    _done(q, spec, "failed", "boom")


def slow_worker(spec: Any, q: Any, cancel: Any) -> None:
    _touch(spec)
    cancel.wait(30)
    _done(q, spec, "cancelled" if cancel.is_set() else "succeeded")


def crash_worker(spec: Any, q: Any, cancel: Any) -> None:
    _touch(spec)
    os._exit(1)


def stubborn_worker(spec: Any, q: Any, cancel: Any) -> None:
    _touch(spec)
    time.sleep(60)


def sigterm_proof_worker(spec: Any, q: Any, cancel: Any) -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    _touch(spec)  # readiness marker: handler is installed
    time.sleep(60)


def incremental_worker(spec: Any, q: Any, cancel: Any) -> None:
    q.put(
        (
            "done",
            spec.job_id,
            {"status": "succeeded", "error": None, "counters": {"incremental": spec.incremental}},
        )
    )
    q.close()
    q.join_thread()


def silent_exit_worker(spec: Any, q: Any, cancel: Any) -> None:
    _touch(spec)  # exits 0 without ever sending done


def silent_after_cancel_worker(spec: Any, q: Any, cancel: Any) -> None:
    _touch(spec)
    cancel.wait(30)
