"""Module-level spawn targets for supervisor tests (spawn needs importable functions)."""

import os
import signal
import threading
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


def fast_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    q.put(("event", spec.job_id, {"type": "phase", "name": "starting"}))
    _done(q, spec, "succeeded")


def failing_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    _done(q, spec, "failed", "boom")


def slow_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    cancel.wait(30)
    _done(q, spec, "cancelled" if cancel.is_set() else "succeeded")


def crash_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    os._exit(1)


def stubborn_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    time.sleep(60)


def sigterm_proof_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    _touch(spec)  # readiness marker: handler is installed
    time.sleep(60)


def stuck_download_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    """Models a download stuck in a gallery-dl hook: ignores cancel and SIGTERM."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def hook() -> None:
        _touch(spec)
        while True:
            time.sleep(0.05)  # never checks `cancel`

    hook()


def incremental_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    q.put(
        (
            "done",
            spec.job_id,
            {"status": "succeeded", "error": None, "counters": {"incremental": spec.incremental}},
        )
    )
    q.close()
    q.join_thread()


def silent_exit_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)  # exits 0 without ever sending done


def silent_after_cancel_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    cancel.wait(30)


def hang_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    time.sleep(60)  # default SIGTERM kills it; never sends done


def renewing_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    _touch(spec)
    jar = ".reddit.com\tTRUE\t/\tTRUE\t4102444800\treddit_session\tNEWVALUE\n"
    q.put(
        (
            "done",
            spec.job_id,
            {"status": "succeeded", "error": None, "counters": {}, "renewed_cookies": jar},
        )
    )
    q.close()
    q.join_thread()


_SHA = b"\x07" * 20


def _claims(spec: Any, q: Any, conn: Any) -> Any:
    from app.runtime.claims import RemoteClaims

    return RemoteClaims(conn, q), threading.Event()


def _mark(spec: Any, name: str, text: str = "x") -> None:
    d = Path(spec.scratch_dir) / str(spec.job_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text)


def claim_release_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    """Claims the content, records it, releases (commit-ordered) and idles until cancelled."""
    claims, never = _claims(spec, q, conn)
    cid = claims.claim_file(spec.target.id, _SHA, None, None, never)
    _mark(spec, "got")
    q.put(
        (
            "record",
            {
                "target_id": spec.target.id,
                "source_id": spec.source.id,
                "key": bytes([spec.job_id]) * 16,
                "sha1": _SHA,
                "phash": None,
                "immich_asset_id": None,
            },
        )
    )
    claims.release_file(cid)
    _mark(spec, "released")
    cancel.wait(30)
    _done(q, spec, "cancelled")


def claim_hold_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    """Claims the content and never releases it (until killed)."""
    claims, never = _claims(spec, q, conn)
    claims.claim_file(spec.target.id, _SHA, None, None, never)
    _mark(spec, "got")
    if spec.job_id == 1:
        _mark(spec, "held", str(os.getpid()))
    cancel.wait(30)
    _done(q, spec, "cancelled")


def claim_leak_worker(spec: Any, q: Any, cancel: Any, conn: Any) -> None:
    claims, never = _claims(spec, q, conn)
    claims.claim_file(spec.target.id, _SHA, None, None, never)
    _done(q, spec, "succeeded")
