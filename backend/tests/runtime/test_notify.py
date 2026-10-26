import logging
from typing import Any

import apprise
import pytest

from app.runtime.notify import notify_job

URL = "json://localhost/"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake(self: Any, body: str = "", title: str = "", **kw: Any) -> bool:
        calls.append({"body": body, "title": title})
        return True

    monkeypatch.setattr(apprise.Apprise, "notify", fake)
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

    monkeypatch.setattr(apprise.Apprise, "notify", boom)
    with caplog.at_level(logging.WARNING):
        await notify_job(1, "s", {}, "failed", "x", [URL], ["failure"])
    assert "notification failed" in caplog.text
