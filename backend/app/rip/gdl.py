"""gallery-dl runner: process-global config, own archive, hooks, log capture, SSRF guard."""

import collections
import contextlib
import ipaddress
import json
import logging
import os
import re
import socket
import threading
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import urllib3.util.connection as _uconn
from gallery_dl import cache, config, exception, formatter, job

from app.core.extractors import _ip_private, validate_gdl_options
from app.db.models import CredentialKind
from app.rip.dedupe import url_key
from app.rip.filters import gdl_filter_options
from app.rip.settings import RateLimit, RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot

VIDEO_EXTS = ("mp4", "webm", "mkv", "mov", "m4v", "avi", "gifv")
_CRED_KEY = re.compile(r"^[a-z][a-z-]{1,40}$")
_CRED_DENY = {
    "postprocessors",
    "postprocessor",
    "postprocessor-options",
    "exec",
    "directory",
    "filename",
    "base-directory",
    "cookies",
    "proxy",
    "skip",
    "cache",
    "download",
}


def _no_cache() -> None:
    return None


def _credential_options(cred: CredentialSnapshot, job_dir: Path) -> dict[str, Any]:
    """Return extractor.<site> options for a credential (cookies written to job_dir)."""
    secret = cred.secret.get_secret_value()
    if cred.kind == CredentialKind.cookies:
        path = job_dir / ".cookies.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secret)
        os.chmod(path, 0o600)
        return {"cookies": str(path)}
    data = json.loads(secret)
    if not isinstance(data, dict):
        raise ValueError("credential secret must be a JSON object")
    if cred.kind == CredentialKind.userpass:
        return {"username": data["username"], "password": data["password"]}
    out: dict[str, Any] = {}
    for k, v in data.items():
        if (
            not _CRED_KEY.match(k)
            or k.endswith("-filter")
            or k.startswith("archive")
            or k in _CRED_DENY
        ):
            raise ValueError(f"credential key not allowed: {k}")
        if not isinstance(v, str | int | float | bool):
            raise ValueError(f"credential value must be a scalar: {k}")
        out[k] = v
    return out


def configure(
    src: SourceSnapshot,
    cred: CredentialSnapshot | None,
    settings: RipSettings,
    job_dir: Path,
    incremental: bool,
) -> None:
    config.clear()
    # gallery-dl's on-disk cache lives under $HOME; nothing may persist outside job_dir.
    cache.database = _no_cache
    ext: tuple[str, ...] = ("extractor",)
    config.set(ext, "base-directory", str(job_dir))
    config.set(ext, "file-filter", f"extension not in {VIDEO_EXTS!r}")
    config.set(("extractor", "reddit"), "videos", False)
    for k, v in validate_gdl_options(src.gdl_options).items():
        config.set(ext, k, v)
    fo = gdl_filter_options(src.filters, src.backfill_mode, src.backfill_value, incremental)
    for k, v in fo["extractor"].items():
        config.set(ext, k, v)
    for k, v in fo["downloader"].items():
        config.set(("downloader",), k, v)
    proxy = src.proxy or settings.proxy
    if proxy:
        config.set(ext, "proxy", proxy)
        config.set(("downloader",), "proxy", proxy)
    rl = settings.rate_limits.get(src.extractor) or settings.rate_limits.get("default")
    rl = rl or RateLimit()
    cat = ("extractor", src.extractor)
    config.set(cat, "sleep-request", rl.sleep_request)
    config.set(cat, "sleep", rl.sleep)
    config.set(cat, "retries", rl.retries)
    config.set(("downloader",), "retries", rl.retries)
    if cred is not None:
        for k, v in _credential_options(cred, job_dir).items():
            config.set(("extractor", cred.site), k, v)


class _Archive:
    """Duck-typed stand-in for gallery-dl's DownloadArchive; `add` is never relied on."""

    def __init__(self, keygen: Callable[[dict[str, Any]], str], check: Callable[[bytes], bool]):
        self._keygen = keygen
        self._check = check

    def check(self, kwdict: dict[str, Any]) -> bool:
        key = kwdict["_archive_key"] = self._keygen(kwdict)
        return self._check(url_key(kwdict["category"], key))

    def add(self, kwdict: dict[str, Any]) -> None:
        pass

    def finalize(self) -> None:
        pass

    def close(self) -> None:
        pass


class HoarderJob(job.DownloadJob):  # type: ignore[misc]
    def __init__(
        self,
        url: str,
        *,
        archive_check: Callable[[bytes], bool],
        on_discovered: Callable[[dict[str, Any]], None],
        on_file: Callable[[Path, dict[str, Any]], None],
        cancel: threading.Event,
    ) -> None:
        super().__init__(url)
        self._archive_check = archive_check
        self._on_discovered = on_discovered
        self._on_file = on_file
        self._cancel = cancel

    def initialize(self, kwdict: dict[str, Any] | None = None) -> None:
        super().initialize(kwdict)
        extr = self.extractor
        cfg = extr.config
        prefix = cfg("archive-prefix")
        if prefix is None:
            prefix = extr.category
        fmt = cfg("archive-format") or extr.archive_fmt
        keygen = formatter.parse(prefix + fmt).format_map
        self.archive = _Archive(keygen, self._archive_check)
        self._archive_write_file = False
        self._archive_write_skip = False
        self._archive_write_after = False
        if not self.hooks:
            self.hooks: Any = collections.defaultdict(list)
        self.register_hooks({"prepare": self._prepare, "after": self._after}, None)

    def _prepare(self, pathfmt: Any) -> None:
        if self._cancel.is_set():
            raise exception.StopExtraction()
        self._on_discovered(pathfmt.kwdict)

    def _after(self, pathfmt: Any) -> None:
        kw = pathfmt.kwdict
        key = url_key(kw["category"], kw["_archive_key"])
        self._on_file(Path(pathfmt.realpath), dict(kw) | {"_key": key})


_LEVELS = {
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "trace": logging.DEBUG,
}


class _EmitHandler(logging.Handler):
    def __init__(self, emit_fn: Callable[[dict[str, Any]], None], level: int) -> None:
        super().__init__(level)
        self._emit = emit_fn

    def emit(self, record: logging.LogRecord) -> None:
        self._emit(
            {
                "type": "log",
                "level": record.levelname.lower(),
                "msg": record.getMessage(),
                "logger": record.name,
            }
        )


@contextlib.contextmanager
def capture_logs(
    emit: Callable[[dict[str, Any]], None], level: str, categories: Iterable[str] = ()
) -> Iterator[None]:
    lvl = _LEVELS.get(level, logging.INFO)
    names = ["gallery-dl", "download", "downloader", "postprocessor", *categories]
    handler = _EmitHandler(emit, lvl)
    saved: list[tuple[logging.Logger, int]] = []
    for n in names:
        lg = logging.getLogger(n)
        saved.append((lg, lg.level))
        lg.setLevel(lvl)
        lg.addHandler(handler)
    try:
        yield
    finally:
        for lg, old in saved:
            lg.removeHandler(handler)
            lg.setLevel(old)


def _blocked(ip_s: str) -> bool:
    ip = ipaddress.ip_address(ip_s.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        p = ip.packed
        if p[:12] == bytes(12) or p[:12] == bytes.fromhex("0064ff9b" + "00" * 8):
            ip = ipaddress.IPv4Address(p[12:])
    return _ip_private(ip)


@contextlib.contextmanager
def ssrf_guard(allow_private: bool, exempt_hosts: set[str]) -> Iterator[None]:
    """Connect-time guard: resolve once, vet every address, connect to the vetted IP."""
    if allow_private:
        yield
        return
    orig = _uconn.create_connection
    exempt = {h.lower() for h in exempt_hosts}

    def guarded(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
        host, port = address
        host = host.strip("[]")
        if host.lower() in exempt:
            return orig(address, *args, **kwargs)
        try:
            infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise OSError(f"name resolution failed: {e}") from e
        ips = [str(i[4][0]) for i in infos]
        if not ips or any(_blocked(ip) for ip in ips):
            raise OSError("blocked private address")
        err: OSError | None = None
        for ip in ips:
            try:
                return orig((ip, port), *args, **kwargs)
            except OSError as e:
                err = e
        raise err or OSError("connection failed")

    _uconn.create_connection = guarded
    try:
        yield
    finally:
        _uconn.create_connection = orig


def run_job(job_: HoarderJob, src: SourceSnapshot, settings: RipSettings) -> int:
    """Run inside the SSRF guard; the proxy host is exempt."""
    proxy = src.proxy or settings.proxy
    exempt = {h} if proxy and (h := urlsplit(proxy).hostname) else set()
    with ssrf_guard(settings.allow_private_hosts, exempt):
        return int(job_.run())
