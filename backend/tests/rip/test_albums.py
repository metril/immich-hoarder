import threading
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.immich.client import ImmichClient
from app.immich.errors import ImmichUnavailable
from app.rip.albums import ALBUM_FIELDS, AlbumResolver, render_album

BASE = "http://immich.test/api"


@pytest.fixture
def client() -> Iterator[ImmichClient]:
    with respx.mock:
        with ImmichClient("http://immich.test", "k", sleep=lambda _s: None) as c:
            yield c


def test_fields() -> None:
    assert ALBUM_FIELDS == {"subreddit", "author", "user", "site", "category", "source", "date"}


def test_render_subreddit() -> None:
    meta = {
        "subreddit": "cats",
        "category": "reddit",
        "author": "bob",
        "date": datetime(2024, 3, 9, tzinfo=UTC),
    }
    assert render_album("Reddit/{subreddit}", meta, "S") == "Reddit/cats"
    assert render_album("{site}-{user}-{date}-{source}", meta, "S") == "reddit-bob-2024-03-S"
    assert render_album("{user}", {"user": "u", "author": "a"}, "S") == "u"


def test_missing_field_falls_back_to_source_name() -> None:
    assert render_album("Reddit/{subreddit}", {}, "S") == "S"
    assert render_album("Reddit/{subreddit}", {"subreddit": ""}, "S") == "S"
    assert render_album("{date}", {"date": "garbage"}, "S") == "S"


def test_spec_and_conversion_fall_back() -> None:
    meta = {"subreddit": "cats"}
    assert render_album("{subreddit!r}", meta, "S") == "S"
    assert render_album("{subreddit:>10}", meta, "S") == "S"
    assert render_album("{bad", meta, "S") == "S"


def test_empty_template_is_source_name() -> None:
    assert render_album("", {}, "S") == "S"
    assert render_album(" / ", {}, "S") == "S"


def test_truncate_and_collapse() -> None:
    assert render_album("/ a   b\t\nc /", {}, "S") == "a b c"
    assert render_album("{subreddit}", {"subreddit": "x\x00y\x07"}, "S") == "xy"
    assert len(render_album("{subreddit}", {"subreddit": "x" * 400}, "S")) == 255


def test_resolver_uses_existing(client: ImmichClient) -> None:
    lst = respx.get(f"{BASE}/albums").respond(200, json=[{"id": "1", "albumName": "A"}])
    post = respx.post(f"{BASE}/albums")
    r = AlbumResolver(client)
    assert r.resolve("A") == "1"
    assert r.resolve("A") == "1"
    assert lst.call_count == 1
    assert post.call_count == 0
    post.respond(201, json={"id": "2", "albumName": "a"})
    assert r.resolve("a") == "2"  # case-sensitive


def test_resolver_creates_once_under_threads(client: ImmichClient) -> None:
    respx.get(f"{BASE}/albums").respond(200, json=[])
    post = respx.post(f"{BASE}/albums").respond(201, json={"id": "9", "albumName": "N"})
    r = AlbumResolver(client)
    out: list[str] = []
    ts = [threading.Thread(target=lambda: out.append(r.resolve("N"))) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert out == ["9"] * 8
    assert post.call_count == 1


def test_resolver_relists_after_unavailable(client: ImmichClient) -> None:
    lst = respx.get(f"{BASE}/albums").mock(
        side_effect=[
            httpx.Response(200, json=[]),
            httpx.Response(200, json=[{"id": "7", "albumName": "N"}]),
        ]
    )
    post = respx.post(f"{BASE}/albums").respond(504)
    r = AlbumResolver(client)
    with pytest.raises(ImmichUnavailable):
        r.resolve("N")
    assert r.resolve("N") == "7"
    assert lst.call_count == 2
    assert post.call_count == 1


def test_resolver_relists_after_list_failure(client: ImmichClient) -> None:
    state = {"fail": True}

    def handler(_req: httpx.Request) -> httpx.Response:
        if state["fail"]:
            return httpx.Response(504)
        return httpx.Response(200, json=[{"id": "7", "albumName": "N"}])

    respx.get(f"{BASE}/albums").mock(side_effect=handler)
    post = respx.post(f"{BASE}/albums").respond(201, json={"id": "9", "albumName": "N"})
    r = AlbumResolver(client)
    with pytest.raises(ImmichUnavailable):
        r.resolve("N")
    state["fail"] = False
    assert r.resolve("N") == "7"
    assert post.call_count == 0


def test_resolver_invalidates_on_immich_error(client: ImmichClient) -> None:
    from app.immich.errors import ImmichError

    lst = respx.get(f"{BASE}/albums").respond(200, json=[])
    respx.post(f"{BASE}/albums").respond(500)
    r = AlbumResolver(client)
    with pytest.raises(ImmichError):
        r.resolve("N")
    with pytest.raises(ImmichError):
        r.resolve("N")
    assert lst.call_count == 2


def test_non_scalar_values_are_missing() -> None:
    assert render_album("{user}", {"user": {"name": "x"}}, "S") == "S"
    assert render_album("{subreddit}", {"subreddit": ["a"]}, "S") == "S"
    assert render_album("{subreddit}", {"subreddit": True}, "S") == "S"
    assert render_album("{subreddit}", {"subreddit": 42}, "S") == "42"
    assert render_album("{user}", {"user": {"n": 1}, "author": "bob"}, "S") == "S"


def test_fallback_sanitised_and_restripped() -> None:
    assert render_album("", {}, "  a\x00b / ") == "ab"
    assert render_album("{subreddit}", {"subreddit": "x" * 254 + " /y"}, "S") == "x" * 254
    assert render_album("{subreddit}", {"subreddit": "a​b\ud800c"}, "S") == "abc"
