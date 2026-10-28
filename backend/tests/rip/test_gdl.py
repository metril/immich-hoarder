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
from app.rip.cookies import CredentialError
from app.rip.filters import FilterSpec
from app.rip.gdl import HoarderJob, capture_logs, configure, run_job, ssrf_guard
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

    def go(
        self, url: str, *, allow_private: bool = True, exempt: set[tuple[str, int]] | None = None
    ) -> int:
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
    assert config.get(("extractor", "reddit"), "follow") is None
    assert config.get(("extractor", "reddit"), "username") is None


@pytest.mark.parametrize(
    "key",
    [
        "postprocessors",
        "exec",
        "file-filter",
        "image-filter",
        "Bad",
        "a",
        "directory",
        "follow",
        "path-restrict",
        "write-pages",
        "netrc",
        "verify",
        "proxy-env",
        "source-address",
        "whitelist",
        "blacklist",
    ],
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
    assert run.go(url, allow_private=False, exempt={("pub.example", int(port))}) != 0
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


def test_hardened_defaults_hold(tmp_path: Path) -> None:
    configure(src(gdl_options={}), None, FAST, tmp_path, incremental=False)
    ext = ("extractor",)
    assert config.get(ext, "path-restrict") == "auto"
    assert config.get(ext, "netrc") is False
    assert config.get(ext, "verify") is True
    assert config.get(ext, "proxy-env") is False
    assert config.get(ext, "write-pages") is False


def test_ytdl_unavailable() -> None:
    from gallery_dl import downloader, extractor

    assert extractor.find("ytdl:https://example.com/v") is None
    assert downloader.find("ytdl") is None


def test_ssrf_guard_does_not_nest() -> None:
    with ssrf_guard(False, set()), pytest.raises(RuntimeError), ssrf_guard(True, set()):
        pass
    with ssrf_guard(True, set()):
        pass  # released after the failed nesting


def test_private_src_proxy_is_blocked(tmp_path: Path, img_server: str) -> None:
    port = int(img_server.rsplit(":", 1)[1])
    s = src(proxy=img_server)  # private proxy chosen by a source owner
    d = tmp_path / "j"
    d.mkdir()
    configure(s, None, FAST, d, incremental=False)
    files: list[Any] = []
    j = HoarderJob(
        "http://pub.example/img/a.jpg",
        archive_check=lambda k: False,
        on_discovered=lambda m: None,
        on_file=lambda p, m: files.append(p),
        cancel=threading.Event(),
    )
    # settings.proxy is a different (admin) proxy; src.proxy gets no exemption
    settings = FAST.model_copy(update={"proxy": f"http://127.0.0.1:{port + 1}"})
    assert run_job(j, s, settings) != 0
    assert files == []


def test_admin_proxy_pair_is_exempt(tmp_path: Path, img_server: str) -> None:
    port = int(img_server.rsplit(":", 1)[1])
    d = tmp_path / "j"
    d.mkdir()
    settings = FAST.model_copy(update={"proxy": img_server})
    configure(src(), None, settings, d, incremental=False)
    j = HoarderJob(
        "http://pub.example/img/a.jpg",
        archive_check=lambda k: False,
        on_discovered=lambda m: None,
        on_file=lambda p, m: None,
        cancel=threading.Event(),
    )
    # connection to the admin proxy (host, port) must not be rejected by the guard
    import urllib3.util.connection as uc

    seen: list[Any] = []
    real = uc.create_connection

    def spy(addr: Any, *a: Any, **k: Any) -> Any:
        seen.append(addr)
        return real(addr, *a, **k)

    uc.create_connection = spy
    try:
        run_job(j, src(), settings)
    finally:
        uc.create_connection = real
    assert ("127.0.0.1", port) in seen


def test_child_job_inherits_callbacks(
    run: Run, img_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orig = directlink.DirectlinkExtractor.items
    child_url = f"{img_server}/img/b.png"

    def items(self: Any) -> Iterator[tuple[Any, ...]]:
        if self.url.endswith("a.jpg"):
            yield Message.Queue, child_url, {"_extractor": directlink.DirectlinkExtractor}
        else:
            yield from orig(self)

    monkeypatch.setattr(directlink.DirectlinkExtractor, "items", items)
    assert run.go(f"{img_server}/img/a.jpg") == 0
    assert [p.suffix for p, _ in run.files] == [".png"]


def test_dotdot_directory_cannot_escape(tmp_path: Path, img_server: str) -> None:
    jd = tmp_path / "a" / "b" / "job"
    jd.mkdir(parents=True)
    configure(src(), None, FAST, jd, incremental=False)
    config.set(("extractor",), "directory", ["..", "..", "escaped"])
    r = Run(jd)
    events: list[dict[str, Any]] = []
    with capture_logs(events.append, "warn", categories=["directlink"]):
        r.go(f"{img_server}/img/a.jpg")
    assert r.files == []
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
    assert any(e["level"] == "warning" for e in events)


def test_user_rate_options_never_faster_than_admin(tmp_path: Path) -> None:
    admin = RipSettings(rate_limits={"default": RateLimit(sleep_request=2, sleep=1, retries=3)})
    cat = ("extractor", "directlink")
    fast = src(gdl_options={"sleep-request": 0.1, "sleep": 0, "retries": 1})
    configure(fast, None, admin, tmp_path, incremental=False)
    assert config.get(cat, "sleep-request") == 2
    assert config.get(cat, "sleep") == 1
    assert config.get(cat, "retries") == 3
    slow = src(gdl_options={"sleep-request": 9, "sleep": [3, 5], "retries": 8})
    configure(slow, None, admin, tmp_path, incremental=False)
    assert config.get(cat, "sleep-request") == 9
    assert config.get(cat, "sleep") == [3, 5]
    assert config.get(cat, "retries") == 8
    odd = src(gdl_options={"sleep-request": "fast"})
    configure(odd, None, admin, tmp_path, incremental=False)
    assert config.get(cat, "sleep-request") == 2


def test_ip_private_denies_site_local() -> None:
    import ipaddress

    from app.core.extractors import _ip_private

    assert _ip_private(ipaddress.ip_address("fec0::1"))
    assert _ip_private(ipaddress.ip_address("fec0:1:2::3"))
    assert not _ip_private(ipaddress.ip_address("2606:4700::1111"))


def test_user_rate_options_reject_non_finite_and_non_int_retries(tmp_path: Path) -> None:
    admin = RipSettings(rate_limits={"default": RateLimit(sleep_request=2, sleep=1, retries=3)})
    cat = ("extractor", "directlink")
    for bad in (float("nan"), float("inf")):
        configure(
            src(gdl_options={"sleep-request": bad, "sleep": bad}), None, admin, tmp_path, False
        )
        assert config.get(cat, "sleep-request") == 2
        assert config.get(cat, "sleep") == 1
    configure(src(gdl_options={"retries": 3.5}), None, admin, tmp_path, incremental=False)
    assert config.get(cat, "retries") == 3
    assert config.get(("downloader",), "retries") == 3


def test_handle_url_overwrites_shared_kwdict_file_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        "gallery_dl.job.DownloadJob.handle_url", lambda self, url, kw: seen.append(kw["_file_url"])
    )
    job = HoarderJob(
        "http://x/a.jpg",
        archive_check=lambda k: False,
        on_discovered=lambda m: None,
        on_file=lambda p, m: None,
        cancel=threading.Event(),
    )
    kw: dict[str, Any] = {}
    job.handle_url("http://x/1.jpg?token=s", kw)
    job.handle_url("http://x/2.jpg", kw)
    assert seen == ["http://x/1.jpg", "http://x/2.jpg"]


def _cookie_cred(secret: str, site: str = "reddit") -> CredentialSnapshot:
    return CredentialSnapshot(site=site, kind=CredentialKind.cookies, secret=SecretStr(secret))


def _cookie_text(tmp_path: Path, secret: str, site: str = "reddit") -> str:
    configure(src(), _cookie_cred(secret, site), FAST, tmp_path, incremental=False)
    return Path(config.get(("extractor", site), "cookies")).read_text()


NS = (
    "# Netscape HTTP Cookie File\n"
    ".reddit.com\tTRUE\t/\tTRUE\t0\treddit_session\tabc123\n"
    "#HttpOnly_.reddit.com\tTRUE\t/\tTRUE\t0\tloid\txyz789\n"
)


def test_netscape_passthrough_as_is(tmp_path: Path) -> None:
    assert _cookie_text(tmp_path, NS) == NS
    assert _cookie_text(tmp_path, "# Netscape\n", "directlink") == "# Netscape\n"


JSON_LIST = [
    {
        "name": "reddit_session",
        "value": "abc123",
        "domain": ".reddit.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "expirationDate": 1900000000.5,
    },
    {"name": "pref", "value": "v1", "domain": "www.reddit.com", "path": "/x", "session": True},
]


def test_json_list_converted(tmp_path: Path) -> None:
    rows = _cookie_text(tmp_path, json.dumps(JSON_LIST)).splitlines()
    assert rows[1] == "#HttpOnly_.reddit.com\tTRUE\t/\tTRUE\t1900000000\treddit_session\tabc123"
    assert rows[2] == "www.reddit.com\tFALSE\t/x\tFALSE\t0\tpref\tv1"


def test_json_wrapper_converted(tmp_path: Path) -> None:
    text = _cookie_text(tmp_path, json.dumps({"cookies": JSON_LIST}))
    assert "reddit_session\tabc123" in text


def test_reddit_header_string(tmp_path: Path) -> None:
    text = _cookie_text(tmp_path, "Cookie: reddit_session=abc; loid=x")
    rows = text.splitlines()[1:]
    assert rows == [
        ".reddit.com\tTRUE\t/\tTRUE\t0\treddit_session\tabc",
        ".reddit.com\tTRUE\t/\tTRUE\t0\tloid\tx",
    ]


def test_reddit_missing_session_raises(tmp_path: Path) -> None:
    for secret in ("loid=abc; foo=bar", ".reddit.com\tTRUE\t/\tTRUE\t0\tloid\tabc\n"):
        with pytest.raises(CredentialError, match="missing reddit_session"):
            configure(src(), _cookie_cred(secret), FAST, tmp_path, incremental=False)


def test_reddit_api_rest_set_without_client_id(tmp_path: Path) -> None:
    configure(src(), _cookie_cred(NS), FAST, tmp_path, incremental=False)
    assert config.get(("extractor", "reddit"), "api") == "rest"
    assert config.get(("extractor", "reddit"), "client-id") is None


@pytest.mark.parametrize("secret", ["a=b; c=d", "Cookie: a=b"])
def test_non_reddit_header_string_raises(tmp_path: Path, secret: str) -> None:
    with pytest.raises(CredentialError, match="Netscape cookies.txt or a JSON export"):
        configure(src(), _cookie_cred(secret, "pixiv"), FAST, tmp_path, incremental=False)


@pytest.mark.parametrize("secret", ["garbage", "[1, 2]", "{}", "[{bad", "[]"])
def test_garbage_cookies_raise(tmp_path: Path, secret: str) -> None:
    with pytest.raises(CredentialError, match="Netscape cookies.txt or a JSON export"):
        configure(src(), _cookie_cred(secret, "pixiv"), FAST, tmp_path, incremental=False)


def test_reddit_oauth_credential_default_and_custom_user_agent(tmp_path: Path) -> None:
    from app import __version__

    def cred(d: dict[str, Any]) -> CredentialSnapshot:
        return CredentialSnapshot(
            site="reddit", kind=CredentialKind.oauth, secret=SecretStr(json.dumps(d))
        )

    configure(src(), cred({"client-id": "c", "refresh-token": "r"}), FAST, tmp_path, False)
    assert config.get(("extractor", "reddit"), "user-agent") == f"immich-hoarder/{__version__}"
    configure(src(), cred({"client-id": "c", "user-agent": "mine"}), FAST, tmp_path, False)
    assert config.get(("extractor", "reddit"), "user-agent") == "mine"


def test_reddit_tls_defaults(tmp_path: Path) -> None:
    configure(src(), None, FAST, tmp_path, incremental=False)
    assert config.get(("extractor", "reddit"), "ciphers") == "chrome"
    assert config.get(("extractor", "reddit"), "tls12") is False


def test_user_option_overrides_reddit_tls(tmp_path: Path) -> None:
    o = {"reddit": {"browser": "firefox", "tls12": True}}
    configure(src(gdl_options=o), None, FAST, tmp_path, incremental=False)
    assert config.get(("extractor", "reddit"), "browser") == "firefox"
    assert config.get(("extractor", "reddit"), "tls12") is True


def test_global_user_option(tmp_path: Path) -> None:
    configure(src(gdl_options={"browser": "chrome"}), None, FAST, tmp_path, incremental=False)
    assert config.get(("extractor",), "browser") == "chrome"


def test_per_site_sleep_floored(tmp_path: Path) -> None:
    admin = RipSettings(rate_limits={"default": RateLimit(sleep_request=2.0, sleep=1, retries=3)})
    o = {"reddit": {"sleep-request": 0.1, "sleep": 0, "retries": 1}}
    configure(src(gdl_options=o), None, admin, tmp_path, incremental=False)
    assert config.get(("extractor", "reddit"), "sleep-request") == 2.0
    assert config.get(("extractor", "reddit"), "sleep") == 1
    assert config.get(("extractor", "reddit"), "retries") == 3


@pytest.mark.parametrize(
    "opts",
    [
        {"verify": False},
        {"netrc": True},
        {"proxy-env": True},
        {"write-pages": True},
        {"path-restrict": "unix"},
        {"file-filter": "True"},
        {"reddit": {"verify": False}},
    ],
)
def test_hardening_cannot_be_overridden(tmp_path: Path, opts: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        configure(src(gdl_options=opts), None, FAST, tmp_path, incremental=False)


def test_top_level_rate_options_floored(tmp_path: Path) -> None:
    admin = RipSettings(rate_limits={"default": RateLimit(sleep_request=2.0, sleep=1, retries=3)})
    o = {"sleep-request": 0, "sleep": 0, "retries": 0}
    configure(src(gdl_options=o), None, admin, tmp_path, incremental=False)
    assert config.get(("extractor",), "sleep-request") == 2.0
    assert config.get(("extractor",), "sleep") == 1
    assert config.get(("extractor",), "retries") == 3


@pytest.mark.parametrize("ua", ["browser", "@firefox"])
def test_credential_user_agent_rejected(tmp_path: Path, ua: str) -> None:
    cred = CredentialSnapshot(
        site="reddit",
        kind=CredentialKind.token,
        secret=SecretStr(json.dumps({"client-id": "x", "user-agent": ua})),
    )
    with pytest.raises(ValueError):
        configure(src(), cred, FAST, tmp_path, incremental=False)
