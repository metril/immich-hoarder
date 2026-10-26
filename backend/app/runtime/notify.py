"""Job notifications via apprise. Never raises; never logs URLs or secrets."""

import asyncio
import contextlib
import logging
import socket
import threading
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import apprise
from apprise.url import URLBase

from app.rip.gdl import _blocked
from app.rip.scrub import scrub

log = logging.getLogger(__name__)

TIMEOUT_S = 15.0
_MIN_URL_LEN = 4


def _literal_private(host: str) -> bool:
    """Only localhost and literal non-global IPs; numeric ids (discord, telegram) pass."""
    host = host.strip("[]").rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return _blocked(host)
    except ValueError:
        return False


_gate = threading.local()
_real_getaddrinfo = socket.getaddrinfo
_install_lock = threading.Lock()
_installed = False


def _guarded_getaddrinfo(*args: Any, **kwargs: Any) -> Any:
    infos = _real_getaddrinfo(*args, **kwargs)
    if getattr(_gate, "active", False) and any(_blocked(str(i[4][0])) for i in infos):
        raise OSError("blocked private address")
    return infos


def install_connect_guard() -> None:
    """Idempotently wrap socket.getaddrinfo; inert unless the thread gate is set.

    Every connect (urllib3, smtplib, raw-socket plugins) resolves through it.
    """
    global _installed
    with _install_lock:
        if not _installed:
            socket.getaddrinfo = _guarded_getaddrinfo
            _installed = True


@contextlib.contextmanager
def gated(block_private: bool) -> Iterator[None]:
    if not block_private:
        yield
        return
    install_connect_guard()
    _gate.active = True
    try:
        yield
    finally:
        _gate.active = False


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
    if not allow_private and _literal_private(host):
        raise ValueError("private notification host not allowed")


def should_notify(status: str, counters: dict[str, Any], on: Sequence[str]) -> bool:
    if status == "failed" and "failure" in on:
        return True
    if status == "succeeded" and "success" in on:
        return True
    new = int(counters.get("uploaded", 0) or 0) + int(counters.get("linked", 0) or 0)
    return "new_items" in on and new > 0


def _send(urls: list[str], title: str, body: str, *, block_private: bool = False) -> bool:
    # apprise runs Apprise.notify() on its own executor, so call each plugin directly:
    # every connection then happens in this thread, where the gate is set.
    asset = apprise.AppriseAsset(async_mode=False)
    ap = apprise.Apprise(asset=asset)
    for u in urls:
        ap.add(u, asset=asset)
    if not len(ap):
        return False
    with gated(block_private):
        return all(bool(svc.notify(body=body, title=title)) for svc in ap)


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
    block_private: bool = False,
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
        ok = await asyncio.wait_for(
            asyncio.to_thread(_send, urls, title, body, block_private=block_private), TIMEOUT_S
        )
        if not ok:
            log.warning("job %s: notification not delivered", job_id)
    except Exception as e:
        log.warning("job %s: notification failed (%s)", job_id, type(e).__name__)
