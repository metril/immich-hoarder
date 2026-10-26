import logging
from typing import Any

import apprise
import pytest

from app.runtime.notify import check_notify_url, notify_job

URL = "json://example.com/"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake(self: Any, body: str = "", title: str = "", **kw: Any) -> bool:
        calls.append({"body": body, "title": title})
        return True

    monkeypatch.setattr(apprise.plugins.NotifyBase, "notify", fake)
    return calls


async def test_notify_on_failure_only_by_default(sent: list[dict[str, Any]]) -> None:
    await notify_job(1, "src", {"linked": 0}, "succeeded", None, [URL], ["failure"])
    assert sent == []
    await notify_job(
        1, "src", {}, "failed", "boom token=abcd1234", [URL], ["failure"], fragments=["abcd1234"]
    )
    assert len(sent) == 1
    assert sent[0]["title"] == "immich-hoarder: src failed"
    assert "boom" in sent[0]["body"] and "abcd1234" not in sent[0]["body"]


async def test_new_items_trigger(sent: list[dict[str, Any]]) -> None:
    await notify_job(1, "s", {"uploaded": 0, "linked": 0}, "succeeded", None, [URL], ["new_items"])
    assert sent == []
    await notify_job(1, "s", {"uploaded": 1, "linked": 1}, "succeeded", None, [URL], ["new_items"])
    assert len(sent) == 1
    await notify_job(1, "s", {"linked": 2}, "succeeded", None, [URL], ["success"])
    assert len(sent) == 2


async def test_notify_failure_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(self: Any, *a: Any, **k: Any) -> bool:
        raise RuntimeError("nope")

    monkeypatch.setattr(apprise.plugins.NotifyBase, "notify", boom)
    with caplog.at_level(logging.WARNING):
        await notify_job(1, "s", {}, "failed", "x", [URL], ["failure"])
    assert "notification failed" in caplog.text


@pytest.mark.parametrize(
    "url",
    [
        "json://10.0.0.1/",
        "json://169.254.169.254",
        "json://localhost",
        "json://[::1]/",
    ],
)
def test_check_notify_url_rejects_private(url: str) -> None:
    with pytest.raises(ValueError):
        check_notify_url(url, allow_private=False)
    check_notify_url(url, allow_private=True)


def test_check_notify_url_allows_public_rejects_garbage() -> None:
    check_notify_url("json://example.com/", allow_private=False)
    with pytest.raises(ValueError):
        check_notify_url("not a url", allow_private=True)


def test_check_notify_url_accepts_numeric_ids() -> None:
    check_notify_url("discord://123456789012345678/token", allow_private=False)
    check_notify_url("tgram://123456:abcdef/12345", allow_private=False)


@pytest.fixture
def conn(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Resolver returns a private IP; record any socket connect attempt."""
    import socket

    from app.runtime import notify as nm

    nm.install_connect_guard()
    seen: list[Any] = []

    def rec(self: Any, address: Any) -> None:
        seen.append(address)
        raise OSError("stop")

    monkeypatch.setattr(socket.socket, "connect", rec)
    monkeypatch.setattr(
        nm, "_real_getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", a[1]))]
    )
    return seen


def test_connect_guard_blocks_http_rebind(conn: list[Any]) -> None:
    from app.runtime.notify import _send

    assert _send(["json://rebind.example.com/"], "t", "b", block_private=True) is False
    assert conn == []


def test_connect_guard_blocks_smtp(conn: list[Any]) -> None:
    from app.runtime.notify import _send

    assert _send(["mailto://u:p@smtp.internal.lan"], "t", "b", block_private=True) is False
    assert conn == []


def test_connect_guard_blocks_raw_socket_plugins(conn: list[Any]) -> None:
    # mqtt/xmpp/rsyslog/aprs use raw sockets; mqtt needs paho, so exercise the socket layer.
    import socket

    from app.runtime.notify import gated

    with gated(True), pytest.raises(OSError, match="blocked private address"):
        socket.create_connection(("broker.lan", 1883))
    assert conn == []


def test_connect_guard_off_outside_send_and_for_global(conn: list[Any]) -> None:
    import socket

    from app.runtime.notify import _send

    assert socket.getaddrinfo("anything.lan", 80)[0][4][0] == "10.0.0.5"
    with pytest.raises(OSError, match="stop"):
        socket.create_connection(("anything.lan", 80))
    conn.clear()
    _send(["mailto://u:p@smtp.internal.lan"], "t", "b", block_private=False)
    assert conn  # exempt group reaches the connection


def test_connect_guard_lifted_by_allow_private(conn: list[Any]) -> None:
    from app.runtime.notify import _send

    _send(["json://rebind.example.com/"], "t", "b", block_private=False)
    assert conn
