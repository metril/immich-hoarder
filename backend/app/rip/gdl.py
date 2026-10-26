"""gallery-dl runner: process-global config, own archive, hooks, log capture, SSRF guard."""

import collections
import contextlib
import ipaddress
import json
import logging
import os
import socket
import threading
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import urllib3.util.connection as _uconn
from gallery_dl import cache, config, downloader, exception, extractor, formatter, job

from app.core.extractors import _ip_private, validate_gdl_options
from app.db.models import CredentialKind
from app.rip.dedupe import url_key
from app.rip.filters import gdl_filter_options
from app.rip.settings import RateLimit, RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot

VIDEO_EXTS = ("mp4", "webm", "mkv", "mov", "m4v", "avi", "gifv")
_CRED_ALLOW = frozenset(
    {
        "refresh-token",
        "access-token",
        "api-key",
        "api-secret",
        "client-id",
        "client-secret",
        "token",
        "user-id",
        "username",
        "password",
    }
)

# youtube-dl support executes third-party code paths; make it unreachable.
for _mods in (extractor.modules, downloader.modules):
    if "ytdl" in _mods:
        _mods.remove("ytdl")
extractor._cache.clear()
downloader._cache.pop("ytdl", None)


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
        u, pw = data.get("username"), data.get("password")
        if not isinstance(u, str) or not isinstance(pw, str):
            raise ValueError("userpass needs string username and password")
        return {"username": u, "password": pw}
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k not in _CRED_ALLOW:
            raise ValueError(f"credential key not allowed: {k}")
        if isinstance(v, bool) or not isinstance(v, str | int):
            raise ValueError(f"credential value must be a string or int: {k}")
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
    # forced last: nothing above may weaken these
    config.set(ext, "path-restrict", "auto")
    config.set(ext, "netrc", False)
    config.set(ext, "verify", True)
    config.set(ext, "proxy-env", False)
    config.set(ext, "write-pages", False)
    config.set(("output",), "mode", "null")  # keep stdout clean for JSON-lines consumers


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
    _archive_check: Callable[[bytes], bool]
    _on_discovered: Callable[[dict[str, Any]], None]
    _on_file: Callable[[Path, dict[str, Any]], None]
    _cancel: threading.Event

    def __init__(
        self,
        url: Any,
        parent: "HoarderJob | None" = None,
        *,
        archive_check: Callable[[bytes], bool] | None = None,
        on_discovered: Callable[[dict[str, Any]], None] | None = None,
        on_file: Callable[[Path, dict[str, Any]], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> None:
        super().__init__(url, parent)
        if parent is not None:
            archive_check = archive_check or parent._archive_check
            on_discovered = on_discovered or parent._on_discovered
            on_file = on_file or parent._on_file
            cancel = cancel or parent._cancel
        if archive_check is None or on_discovered is None or on_file is None or cancel is None:
            raise TypeError("archive_check, on_discovered, on_file and cancel are required")
        self._archive_check = archive_check
        self._on_discovered = on_discovered
        self._on_file = on_file
        self._cancel = cancel
        self._escaped = False

    def initialize(self, kwdict: dict[str, Any] | None = None) -> None:
        super().initialize(kwdict)
        extr = self.extractor
        cfg = extr.config
        prefix = cfg("archive-prefix")
        if prefix is None:
            prefix = extr.category
        fmt = cfg("archive-format") or extr.archive_fmt
        keygen = formatter.parse(prefix + fmt).format_map
        self.archive = _Archive(keygen, self._check_seen)
        base = config.get(("extractor",), "base-directory")
        self._root = Path(base).resolve() if base else None
        self._archive_write_file = False
        self._archive_write_skip = False
        self._archive_write_after = False
        if not self.hooks:
            self.hooks: Any = collections.defaultdict(list)
        self.register_hooks({"prepare": self._prepare, "after": self._after}, None)

    def _inside(self, pathfmt: Any) -> bool:
        if self._root is None:
            return True
        try:
            return Path(pathfmt.realpath).resolve().is_relative_to(self._root)
        except (OSError, ValueError):
            return False

    def _check_seen(self, key: bytes) -> bool:
        if self._escaped:
            return True  # treated as already seen: skipped without download
        return self._archive_check(key)

    def _prepare(self, pathfmt: Any) -> None:
        if self._cancel.is_set():
            raise exception.StopExtraction()
        self._on_discovered(pathfmt.kwdict)
        self._escaped = False
        pathfmt.build_path()
        if not self._inside(pathfmt):
            self._escaped = True
            self.log.warning("skipping file whose path escapes the job directory")

    def _after(self, pathfmt: Any) -> None:
        if not self._inside(pathfmt):
            self.log.warning("refusing file whose path escapes the job directory")
            return
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


_SITE_LOCAL = ipaddress.IPv6Network("fec0::/10")
_active = threading.Lock()


def _blocked(ip_s: str) -> bool:
    ip = ipaddress.ip_address(ip_s.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        p = ip.packed
        if p[:12] == bytes(12) or p[:12] == bytes.fromhex("0064ff9b" + "00" * 8):
            ip = ipaddress.IPv4Address(p[12:])
    if isinstance(ip, ipaddress.IPv6Address) and ip in _SITE_LOCAL:
        return True
    return _ip_private(ip)


@contextlib.contextmanager
def ssrf_guard(allow_private: bool, exempt_hosts: set[tuple[str, int]]) -> Iterator[None]:
    """Connect-time guard: resolve once, vet every address, connect to the vetted IP.

    `exempt_hosts` holds (host, port) pairs (the admin proxy). Not re-entrant.
    """
    if not _active.acquire(blocking=False):
        raise RuntimeError("ssrf_guard is already active")
    try:
        if allow_private:
            yield
            return
        orig = _uconn.create_connection
        exempt = {(h.lower(), p) for h, p in exempt_hosts}

        def guarded(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
            host, port = address
            host = host.strip("[]")
            if (host.lower(), port) in exempt:
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
    finally:
        _active.release()


_DEFAULT_PORTS = {"http": 80, "https": 443}


def run_job(job_: HoarderJob, src: SourceSnapshot, settings: RipSettings) -> int:
    """Run inside the SSRF guard. Only the admin proxy (host, port) is exempt."""
    exempt: set[tuple[str, int]] = set()
    if settings.proxy:
        u = urlsplit(settings.proxy)
        if u.hostname:
            exempt.add((u.hostname, u.port or _DEFAULT_PORTS.get(u.scheme, 1080)))
    with ssrf_guard(settings.allow_private_hosts, exempt):
        return int(job_.run())
