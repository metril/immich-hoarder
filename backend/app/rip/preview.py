"""Dry-run preview: list what a source would fetch, without downloading anything."""

import multiprocessing
import tempfile
from collections.abc import Callable
from datetime import date, datetime
from multiprocessing.connection import Connection
from pathlib import Path
from threading import Event
from typing import Any

from gallery_dl import exception
from pydantic import BaseModel

from app.db.models import BackfillMode
from app.rip.filters import check_meta
from app.rip.gdl import HoarderJob, capture_logs, configure, run_job
from app.rip.scrub import scrub, secret_fragments
from app.rip.settings import RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot

PREVIEW_MAX = 50


class PreviewError(Exception):
    pass


class PreviewItem(BaseModel):
    url: str
    title: str | None
    date: str | None
    filename: str
    verdict: str | None


def make_job_dir(scratch: Path) -> Path:
    """Create a private job dir; the caller owns it and must remove it."""
    scratch.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="preview-", dir=scratch))


def _since(src: SourceSnapshot) -> date | None:
    if src.backfill_mode == BackfillMode.since and src.backfill_value:
        return date.fromisoformat(src.backfill_value)
    return None


def _item(kw: dict[str, Any], src: SourceSnapshot) -> PreviewItem:
    d = kw.get("date")
    url = kw.get("url") or kw.get("_url") or kw.get("permalink") or ""
    title = kw.get("title")
    return PreviewItem(
        url=str(url),
        title=str(title) if title else None,
        date=d.isoformat() if isinstance(d, datetime) else None,
        filename=str(kw.get("filename") or ""),
        verdict=check_meta(kw, src.filters, since=_since(src)),
    )


def _summary(errors: list[str], status: int, cred: CredentialSnapshot | None) -> str:
    msg = "; ".join(errors) or f"gallery-dl exited with status {status}"
    return scrub(msg, secret_fragments(cred))[:200]


def preview(
    src: SourceSnapshot,
    cred: CredentialSnapshot | None,
    settings: RipSettings,
    job_dir: Path,
    limit: int = PREVIEW_MAX,
) -> list[PreviewItem]:
    """Run gallery-dl with downloads disabled and collect up to `limit` items.

    `job_dir` is created and removed by the caller.
    """
    from gallery_dl import config

    items: list[PreviewItem] = []
    errors: list[str] = []

    def on_discovered(kw: dict[str, Any]) -> None:
        if len(items) >= limit:
            raise exception.StopExtraction()
        items.append(_item(kw, src))

    def collect(ev: dict[str, Any]) -> None:
        if ev.get("level") == "error":
            errors.append(str(ev.get("msg", "")))

    configure(src, cred, settings, job_dir, incremental=False)
    config.set(("extractor",), "download", False)
    job = HoarderJob(
        src.url,
        archive_check=lambda _k: False,
        on_discovered=on_discovered,
        on_file=lambda _p, _m: None,
        cancel=Event(),
    )
    with capture_logs(
        collect, "error", categories=(src.extractor,), fragments=secret_fragments(cred)
    ):
        status = run_job(job, src, settings)
    if status != 0 and not items:
        raise PreviewError(_summary(errors, status, cred))
    return items[:limit]


def _child(
    conn: Connection,
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    fragments: frozenset[str] = frozenset(),
) -> None:
    try:
        conn.send(("ok", fn(*args)))
    except BaseException as e:
        conn.send(("err", scrub(f"{type(e).__name__}: {e}", fragments)))
    finally:
        conn.close()


def run_in_subprocess[T](
    fn: Callable[..., T],
    *args: Any,
    timeout: float,
    fragments: frozenset[str] = frozenset(),
) -> T:
    """Run `fn(*args)` in a spawned process; kill it on timeout (TimeoutError)."""
    ctx = multiprocessing.get_context("spawn")
    parent, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child_conn, fn, args, fragments), daemon=True)
    proc.start()
    child_conn.close()
    try:
        if not parent.poll(timeout):
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
                proc.join()
            raise TimeoutError("subprocess timed out")
        try:
            kind, val = parent.recv()
        except EOFError:
            raise PreviewError("worker exited unexpectedly") from None
    finally:
        parent.close()
        if proc.is_alive():
            proc.kill()
        proc.join()
    if kind == "err":
        raise PreviewError(val)
    return val  # type: ignore[no-any-return]
