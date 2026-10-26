"""Job notifications via apprise. Never raises; never logs URLs or secrets."""

import asyncio
import logging
import socket
import threading
from collections.abc import Iterable, Sequence
from typing import Any

import apprise
import urllib3.util.connection as _uconn
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
_orig_create = _uconn.create_connection
_install_lock = threading.Lock()
_installed = False


def _guarded_create(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
    if not getattr(_gate, "active", False):
        return _orig_create(address, *args, **kwargs)
    host, port = address
    try:
        infos = socket.getaddrinfo(host.strip("[]"), port, 0, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise OSError(f"name resolution failed: {e}") from e
    ips = [str(i[4][0]) for i in infos]
    if not ips or any(_blocked(ip) for ip in ips):
        raise OSError("blocked private address")
    err: OSError | None = None
    for ip in ips:
        try:
            return _orig_create((ip, port), *args, **kwargs)
        except OSError as e:
            err = e
    raise err or OSError("connection failed")


def install_connect_guard() -> None:
    """Idempotently wrap urllib3's create_connection; inert unless the thread gate is set."""
    global _installed
    with _install_lock:
        if not _installed:
            _uconn.create_connection = _guarded_create
            _installed = True


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
    if block_private:
        install_connect_guard()
        _gate.active = True
    try:
        return all(bool(svc.notify(body=body, title=title)) for svc in ap)
    finally:
        _gate.active = False


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
