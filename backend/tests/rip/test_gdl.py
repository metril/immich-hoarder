import json
import logging
import socket
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from gallery_dl import config
from gallery_dl.extractor import directlink
from gallery_dl.extractor.message import Message
from pydantic import SecretStr

from app.db.models import BackfillMode, CredentialKind
from app.rip.filters import FilterSpec
from app.rip.gdl import HoarderJob, capture_logs, configure, ssrf_guard
from app.rip.settings import RateLimit, RipSettings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot

FAST = RipSettings(rate_limits={"default": RateLimit(sleep_request=0, sleep=0, retries=0)})


def src(**kw: Any) -> SourceSnapshot:
    base: dict[str, Any] = {
        "id": 1,
        "name": "s",
        "url": "http://x/",
        "extractor": "directlink",
        "target_id": 1,
        "album_template": "",
        "backfill_mode": BackfillMode.full,
        "backfill_value": None,
        "allow_animated": False,
        "filters": FilterSpec(),
        "gdl_options": {},
        "proxy": None,
        "log_level": "info",
    }
    return SourceSnapshot(**(base | kw))


class Run:
    def __init__(self, job_dir: Path) -> None:
        self.job_dir = job_dir
        self.files: list[tuple[Path, dict[str, Any]]] = []
        self.discovered: list[dict[str, Any]] = []
        self.cancel = threading.Event()
        self.archive: Callable[[bytes], bool] = lambda k: False

    def go(self, url: str, *, allow_private: bool = True, exempt: set[str] | None = None) -> int:
        job = HoarderJob(
            url,
            archive_check=lambda k: self.archive(k),
            on_discovered=self.discovered.append,
            on_file=lambda p, m: self.files.append((p, m)),
            cancel=self.cancel,
        )
        with ssrf_guard(allow_private, exempt or set()):
            return job.run()


@pytest.fixture
def run(tmp_path: Path) -> Run:
    d = tmp_path / "job"
    d.mkdir()
    configure(src(), None, FAST, d, incremental=False)
    return Run(d)


def test_runs_and_calls_on_file_with_path_inside_job_dir(run: Run, img_server: str) -> None:
    assert run.go(f"{img_server}/img/a.jpg") == 0
    assert len(run.files) == 1
    p, meta = run.files[0]
    assert p.is_file() and p.is_relative_to(run.job_dir)
    assert isinstance(meta["_key"], bytes) and len(meta["_key"]) == 16


def test_archive_check_true_skips_download(run: Run, img_server: str) -> None:
    run.archive = lambda k: True
    run.go(f"{img_server}/img/a.jpg")
    assert run.files == []
    assert len(run.discovered) == 1


def test_archive_key_matches_gallery_dl(run: Run, img_server: str) -> None:
    from app.rip.dedupe import url_key

    seen: list[bytes] = []
    run.archive = lambda k: seen.append(k) or False
    run.go(f"{img_server}/img/a.jpg")
    # directlink archive_fmt == "{domain}/{path}/{filename}.{extension}", prefixed by category
    expect = "directlink" + f"127.0.0.1:{img_server.rsplit(':', 1)[1]}/img/a.jpg"
    assert seen == [url_key("directlink", expect)]
    assert run.files[0][1]["_key"] == seen[0]


def test_video_never_downloaded(run: Run, img_server: str) -> None:
    run.go(f"{img_server}/vid/c.mp4")
    assert run.files == []
    assert not any(run.job_dir.rglob("*.mp4"))


def test_cancel_before_start_stops(run: Run, img_server: str) -> None:
    run.cancel.set()
    run.go(f"{img_server}/img/a.jpg")
    assert run.files == []


def test_config_cleared_between_runs(tmp_path: Path) -> None:
    configure(src(proxy="http://proxy.x:1"), None, FAST, tmp_path, incremental=False)
    assert config.get(("extractor",), "proxy") == "http://proxy.x:1"
    configure(src(), None, FAST, tmp_path, incremental=False)
    assert config.get(("extractor",), "proxy") is None


def test_settings_proxy_fallback_and_rate_limits(tmp_path: Path) -> None:
    s = RipSettings(
        proxy="http://p:1",
        rate_limits={
            "default": RateLimit(sleep_request=2, retries=1),
            "directlink": RateLimit(sleep_request=5, retries=7),
        },
    )
    configure(src(), None, s, tmp_path, incremental=True)
    assert config.get(("extractor",), "proxy") == "http://p:1"
    assert config.get(("extractor", "directlink"), "sleep-request") == 5
    assert config.get(("extractor", "directlink"), "retries") == 7
    assert config.get(("extractor",), "skip") == "abort:20"
    assert config.get(("extractor",), "base-directory") == str(tmp_path)


def test_cookie_file_0600_and_inside_job_dir(tmp_path: Path) -> None:
    cred = CredentialSnapshot(
        site="directlink", kind=CredentialKind.cookies, secret=SecretStr("# Netscape\n")
    )
    configure(src(), cred, FAST, tmp_path, incremental=False)
    path = Path(config.get(("extractor", "directlink"), "cookies"))
    assert path.parent == tmp_path
    assert path.stat().st_mode & 0o777 == 0o600


def test_userpass_and_token_credentials(tmp_path: Path) -> None:
    up = CredentialSnapshot(
        site="reddit",
        kind=CredentialKind.userpass,
        secret=SecretStr(json.dumps({"username": "u", "password": "p"})),
    )
    configure(src(), up, FAST, tmp_path, incremental=False)
    assert config.get(("extractor", "reddit"), "username") == "u"
    assert config.get(("extractor", "reddit"), "password") == "p"
    tok = CredentialSnapshot(
        site="reddit",
        kind=CredentialKind.token,
        secret=SecretStr(json.dumps({"refresh-token": "r"})),
    )
    configure(src(), tok, FAST, tmp_path, incremental=False)
    assert config.get(("extractor", "reddit"), "refresh-token") == "r"
    assert config.get(("extractor", "reddit"), "username") is None


@pytest.mark.parametrize(
    "key", ["postprocessors", "exec", "file-filter", "image-filter", "Bad", "a", "directory"]
)
def test_credential_keys_rejected_for_postprocessors(tmp_path: Path, key: str) -> None:
    cred = CredentialSnapshot(
        site="reddit", kind=CredentialKind.token, secret=SecretStr(json.dumps({key: "x"}))
    )
    with pytest.raises(ValueError):
        configure(src(), cred, FAST, tmp_path, incremental=False)


def test_logs_captured(run: Run, img_server: str) -> None:
    events: list[dict[str, Any]] = []
    with capture_logs(events.append, "debug", categories=["directlink"]):
        run.go(f"{img_server}/img/missing.jpg")
    assert events
    assert all(e["type"] == "log" and {"level", "msg", "logger"} <= e.keys() for e in events)
    assert any(e["level"] == "error" for e in events)


def test_capture_logs_restores_state() -> None:
    names = ["directlink", "download", "downloader", "postprocessor", "gallery-dl"]
    before = [(logging.getLogger(n).level, list(logging.getLogger(n).handlers)) for n in names]
    with capture_logs(lambda e: None, "trace", categories=["directlink"]):
        assert logging.getLogger("download").level == logging.DEBUG
    after = [(logging.getLogger(n).level, list(logging.getLogger(n).handlers)) for n in names]
    assert before == after


def test_incremental_abort_stops_early(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    def items(self: Any) -> Iterator[tuple[Any, ...]]:
        yield Message.Directory, "", {"path": "", "domain": "d"}
        for i in range(5):
            yield (
                Message.Url,
                f"http://127.0.0.1:9/img/{i}.jpg",
                {"domain": "d", "path": "p", "filename": str(i), "extension": "jpg"},
            )

    monkeypatch.setattr(directlink.DirectlinkExtractor, "items", items)
    config.set(("extractor",), "skip", "abort:2")
    run.archive = lambda k: True
    run.go("http://127.0.0.1:9/img/0.jpg")
    assert len(run.discovered) == 2
    assert run.files == []


def _fake_dns(monkeypatch: pytest.MonkeyPatch, table: dict[str, str]) -> None:
    real = socket.getaddrinfo

    def fake(host: Any, *a: Any, **k: Any) -> Any:
        return real(table.get(host, host), *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_ssrf_blocks_private_resolution(
    run: Run, img_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_dns(monkeypatch, {"blocked.example": "127.0.0.1"})
    port = img_server.rsplit(":", 1)[1]
    assert run.go(f"http://blocked.example:{port}/img/a.jpg", allow_private=False) != 0
    assert run.files == []


def test_ssrf_blocks_redirect_to_private(
    run: Run, img_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_dns(monkeypatch, {"pub.example": "127.0.0.1", "evil.example": "127.0.0.1"})
    port = img_server.rsplit(":", 1)[1]
    to = f"http://evil.example:{port}/img/a.jpg"
    url = f"http://pub.example:{port}/redir/a.jpg?to={to}"
    assert run.go(url, allow_private=False, exempt={"pub.example"}) != 0
    assert run.files == []


def test_ssrf_allow_private_works(run: Run, img_server: str) -> None:
    assert run.go(f"{img_server}/img/a.jpg", allow_private=True) == 0
    assert len(run.files) == 1


def test_ssrf_guard_restores_and_rejects_mixed(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib3.util.connection as uc

    orig = uc.create_connection
    with ssrf_guard(False, set()):
        assert uc.create_connection is not orig
    assert uc.create_connection is orig
    real = socket.getaddrinfo

    def mixed(host: Any, port: Any, *a: Any, **k: Any) -> Any:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::7f00:1", port, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mixed)
    with ssrf_guard(False, set()), pytest.raises(OSError, match="blocked private address"):
        uc.create_connection(("m.example", 80), timeout=1)
    monkeypatch.setattr(socket, "getaddrinfo", real)


def test_nothing_written_outside_job_dir(
    tmp_path: Path, img_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for var in ("HOME", "XDG_CACHE_HOME", "APPDATA"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.chdir(tmp_path / "home")
    from gallery_dl import cache

    monkeypatch.setattr(cache, "DATABASE", None)
    monkeypatch.setattr(cache, "ERR", None)
    d = tmp_path / "job"
    d.mkdir()
    configure(src(), None, FAST, d, incremental=False)
    r = Run(d)
    assert r.go(f"{img_server}/img/a.jpg") == 0
    assert list(home.rglob("*")) == []
