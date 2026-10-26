"""Job notifications via apprise. Never raises; never logs URLs or secrets."""

import asyncio
import logging
from collections.abc import Iterable, Sequence
from typing import Any

import apprise
from apprise.url import URLBase

from app.core.extractors import _is_private_host
from app.rip.scrub import scrub

log = logging.getLogger(__name__)

TIMEOUT_S = 15.0
_MIN_URL_LEN = 4


def check_notify_url(url: str, *, allow_private: bool) -> None:
    """Raise ValueError (never echoing the URL) for unparseable or private-host URLs."""
    host: str | None = None
    try:
        parsed = URLBase.parse_url(url, verify_host=False) if "://" in url else None  # type: ignore[no-untyped-call]
        host = parsed.get("host") if parsed else None
    except Exception:
        host = None
    if not host or any(c.isspace() for c in host):
        raise ValueError("invalid notification url")
    if not allow_private and _is_private_host(host):
        raise ValueError("private notification host not allowed")


def should_notify(status: str, counters: dict[str, Any], on: Sequence[str]) -> bool:
    if status == "failed" and "failure" in on:
        return True
    if status == "succeeded" and "success" in on:
        return True
    new = int(counters.get("uploaded", 0) or 0) + int(counters.get("linked", 0) or 0)
    return "new_items" in on and new > 0


def _send(urls: list[str], title: str, body: str) -> bool:
    ap = apprise.Apprise()
    for u in urls:
        ap.add(u)
    return bool(ap.notify(body=body, title=title))


async def notify_job(
    job_id: int,
    source_name: str,
    counters: dict[str, Any],
    status: str,
    error: str | None,
    urls: list[str],
    on: Sequence[str],
    *,
    fragments: Iterable[str] = (),
) -> None:
    try:
        if not urls or not should_notify(status, counters, on):
            return
        lines = [f"{k}: {v}" for k, v in sorted(counters.items())]
        if error:
            lines.append(f"error: {error}")
        secrets = [*fragments, *(u for u in urls if len(u) >= _MIN_URL_LEN)]
        title = scrub(f"immich-hoarder: {source_name} {status}", secrets)
        body = scrub("\n".join(lines) or status, secrets)
        ok = await asyncio.wait_for(asyncio.to_thread(_send, urls, title, body), TIMEOUT_S)
        if not ok:
            log.warning("job %s: notification not delivered", job_id)
    except Exception as e:
        log.warning("job %s: notification failed (%s)", job_id, type(e).__name__)
