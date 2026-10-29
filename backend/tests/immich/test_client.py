import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from app.immich.client import REQUIRED_PERMISSIONS, ImmichClient, missing_permissions
from app.immich.errors import AssetGone, ImmichAuthError, ImmichError, ImmichUnavailable

BASE = "http://immich.test/api"
TS = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(sleeps: list[float]) -> Iterator[ImmichClient]:
    with respx.mock:
        with ImmichClient("http://immich.test//", "secret-key", sleep=sleeps.append) as c:
            yield c


@pytest.fixture
def img(tmp_path: Path) -> Path:
    p = tmp_path / "a.jpg"
    p.write_bytes(b"jpegdata")
    return p


def _upload(c: ImmichClient, p: Path):  # type: ignore[no-untyped-def]
    return c.upload(
        p,
        sha1hex="ab" * 20,
        device_asset_id="reddit-1-0",
        file_created_at=TS,
        file_modified_at=TS,
        filename="a.jpg",
    )


def test_upload_created_and_duplicate(client: ImmichClient, img: Path) -> None:
    route = respx.post(f"{BASE}/assets").mock(
        side_effect=[
            httpx.Response(201, json={"id": "a1", "status": "created"}),
            httpx.Response(200, json={"id": "a2", "status": "duplicate"}),
        ]
    )
    r1 = _upload(client, img)
    assert (r1.asset_id, r1.duplicate) == ("a1", False)
    r2 = _upload(client, img)
    assert (r2.asset_id, r2.duplicate) == ("a2", True)
    req = route.calls[0].request
    assert req.headers["x-immich-checksum"] == "ab" * 20
    assert req.headers["x-api-key"] == "secret-key"
    body = req.read()
    for needle in (
        b'name="assetData"',
        b'name="fileCreatedAt"',
        b"2024-01-02T03:04:05",
        b'name="fileModifiedAt"',
        b'name="filename"',
        b'name="deviceAssetId"',
        b"reddit-1-0",
        b'name="deviceId"',
        b"immich-hoarder",
        b"jpegdata",
    ):
        assert needle in body


def test_upload_retries_without_device_fields_on_400(client: ImmichClient, img: Path) -> None:
    route = respx.post(f"{BASE}/assets").mock(
        side_effect=[
            httpx.Response(400, json={"message": ["property deviceAssetId should not exist"]}),
            httpx.Response(201, json={"id": "a1", "status": "created"}),
            httpx.Response(201, json={"id": "a2", "status": "created"}),
        ]
    )
    assert _upload(client, img).asset_id == "a1"
    assert _upload(client, img).asset_id == "a2"
    assert route.call_count == 3
    assert b"deviceAssetId" in route.calls[0].request.read()
    assert b"deviceAssetId" not in route.calls[1].request.read()
    assert b"deviceId" not in route.calls[1].request.read()
    assert b"deviceId" not in route.calls[2].request.read()


def test_upload_400_unrelated_raises(client: ImmichClient, img: Path) -> None:
    respx.post(f"{BASE}/assets").mock(return_value=httpx.Response(400, json={"message": "bad"}))
    with pytest.raises(ImmichError) as ei:
        _upload(client, img)
    assert ei.value.status == 400


def test_retry_on_503_then_success(client: ImmichClient, sleeps: list[float]) -> None:
    route = respx.get(f"{BASE}/server/ping").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"res": "pong"}),
        ]
    )
    assert client.ping() is True
    assert route.call_count == 3
    assert sleeps == [0.5, 1]


def test_retries_exhausted(client: ImmichClient, sleeps: list[float]) -> None:
    route = respx.get(f"{BASE}/server/version").mock(return_value=httpx.Response(502))
    with pytest.raises(ImmichUnavailable):
        client.version()
    assert route.call_count == 3


def test_connect_error_unavailable(client: ImmichClient) -> None:
    respx.get(f"{BASE}/server/version").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(ImmichUnavailable):
        client.version()


def test_retry_after_header_capped(client: ImmichClient, sleeps: list[float]) -> None:
    respx.get(f"{BASE}/server/ping").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(429, headers={"Retry-After": "120"}),
            httpx.Response(200, json={"res": "pong"}),
        ]
    )
    assert client.ping()
    assert sleeps == [3, 10]


def test_auth_error_401(client: ImmichClient) -> None:
    respx.get(f"{BASE}/api-keys/me").mock(return_value=httpx.Response(401, json={"message": "no"}))
    with pytest.raises(ImmichAuthError):
        client.key_permissions()


def test_version_and_permissions(client: ImmichClient) -> None:
    respx.get(f"{BASE}/server/version").mock(
        return_value=httpx.Response(200, json={"major": 3, "minor": 3, "patch": 5})
    )
    respx.get(f"{BASE}/api-keys/me").mock(
        return_value=httpx.Response(200, json={"permissions": ["all"]})
    )
    assert client.version() == "3.3.5"
    assert client.key_permissions() == ["all"]


def test_ping_false_on_non_pong(client: ImmichClient) -> None:
    respx.get(f"{BASE}/server/ping").mock(return_value=httpx.Response(404))
    assert client.ping() is False


@pytest.mark.parametrize("status", [400, 404])
def test_get_asset_gone_on_400_and_404(client: ImmichClient, status: int) -> None:
    respx.get(f"{BASE}/assets/x").mock(return_value=httpx.Response(status, json={"message": "n"}))
    with pytest.raises(AssetGone):
        client.get_asset("x")


def test_get_asset_ok(client: ImmichClient) -> None:
    respx.get(f"{BASE}/assets/x").mock(
        return_value=httpx.Response(200, json={"id": "x", "isTrashed": True})
    )
    a = client.get_asset("x")
    assert (a.id, a.is_trashed) == ("x", True)


def test_albums(client: ImmichClient) -> None:
    respx.get(f"{BASE}/albums").mock(
        return_value=httpx.Response(200, json=[{"id": "1", "albumName": "A", "assetCount": 2}])
    )
    c = respx.post(f"{BASE}/albums").mock(
        return_value=httpx.Response(201, json={"id": "2", "albumName": "B", "assetCount": 0})
    )
    assert client.list_albums()[0].name == "A"
    assert client.list_albums()[0].asset_count == 2
    assert client.create_album("B").id == "2"
    assert b'"albumName"' in c.calls[0].request.read()


def test_add_to_album_duplicate_is_success(client: ImmichClient) -> None:
    respx.put(f"{BASE}/albums/al/assets").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "a", "success": True},
                {"id": "b", "success": False, "error": "duplicate"},
                {"id": "c", "success": False, "error": "not_found"},
            ],
        )
    )
    assert client.add_to_album("al", ["a", "b", "c"]) == {"a": None, "b": None, "c": "not_found"}


def test_bulk_check_parses_trashed(client: ImmichClient) -> None:
    route = respx.post(f"{BASE}/assets/bulk-upload-check").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": "c1", "action": "accept"},
                    {
                        "id": "c2",
                        "action": "reject",
                        "reason": "duplicate",
                        "assetId": "e",
                        "isTrashed": True,
                    },
                ]
            },
        )
    )
    res = client.bulk_check([("c1", "aa"), ("c2", "bb")])
    assert res["c1"].action == "accept" and res["c1"].asset_id is None
    assert res["c1"].is_trashed is False
    assert (res["c2"].reason, res["c2"].asset_id, res["c2"].is_trashed) == ("duplicate", "e", True)
    assert b'"checksum"' in route.calls[0].request.read()


def test_update_asset(client: ImmichClient) -> None:
    route = respx.put(f"{BASE}/assets/x").mock(return_value=httpx.Response(200, json={}))
    client.update_asset("x", description="d", date_time_original=TS)
    body = route.calls[0].request.read()
    assert b'"description"' in body and b'"dateTimeOriginal"' in body
    client.update_asset("x", description=None, date_time_original=None)
    assert route.call_count == 1


def test_missing_permissions() -> None:
    assert missing_permissions(["all"]) == []
    assert missing_permissions(REQUIRED_PERMISSIONS) == []
    assert missing_permissions(["asset.upload", "asset.read"]) == [
        p for p in REQUIRED_PERMISSIONS if p not in ("asset.upload", "asset.read")
    ]


def test_upload_read_timeout_not_retried(client: ImmichClient, img: Path) -> None:
    route = respx.post(f"{BASE}/assets").mock(side_effect=httpx.ReadTimeout("t"))
    with pytest.raises(ImmichUnavailable):
        _upload(client, img)
    assert route.call_count == 1


def test_upload_retry_503_resends_file(client: ImmichClient, img: Path) -> None:
    route = respx.post(f"{BASE}/assets").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(201, json={"id": "a", "status": "created"}),
        ]
    )
    assert _upload(client, img).asset_id == "a"
    assert b"jpegdata" in route.calls[1].request.read()


def test_create_album_not_retried_on_504(client: ImmichClient) -> None:
    route = respx.post(f"{BASE}/albums").mock(return_value=httpx.Response(504))
    with pytest.raises(ImmichUnavailable):
        client.create_album("B")
    assert route.call_count == 1


def test_create_album_retried_on_503(client: ImmichClient) -> None:
    route = respx.post(f"{BASE}/albums").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(201, json={"id": "2", "albumName": "B", "assetCount": 0}),
        ]
    )
    assert client.create_album("B").id == "2"
    assert route.call_count == 2


def test_connect_error_is_retried(client: ImmichClient) -> None:
    route = respx.get(f"{BASE}/server/ping").mock(
        side_effect=[httpx.ConnectError("x"), httpx.Response(200, json={"res": "pong"})]
    )
    assert client.ping()
    assert route.call_count == 2


def test_bulk_check_empty_no_request(client: ImmichClient) -> None:
    route = respx.post(f"{BASE}/assets/bulk-upload-check")
    assert client.bulk_check([]) == {}
    assert route.call_count == 0


def test_ping_false_on_connection_failure_and_bad_body(client: ImmichClient) -> None:
    respx.get(f"{BASE}/server/ping").mock(side_effect=httpx.ConnectError("x"))
    assert client.ping() is False
    respx.get(f"{BASE}/server/ping").mock(return_value=httpx.Response(200, text="<html>"))
    assert client.ping() is False


def test_invalid_response_raises_immich_error(client: ImmichClient) -> None:
    respx.get(f"{BASE}/server/version").respond(200, text="<html>nope</html>")
    with pytest.raises(ImmichError) as ei:
        client.version()
    assert ei.value.status == 200
    respx.get(f"{BASE}/albums").respond(200, json=[{"id": "1"}])
    with pytest.raises(ImmichError):
        client.list_albums()


def test_client_thumbnail(client: ImmichClient) -> None:
    route = respx.get(f"{BASE}/assets/x/thumbnail").mock(
        return_value=httpx.Response(200, content=b"abc", headers={"content-type": "image/webp"})
    )
    assert client.thumbnail("x", "preview") == (b"abc", "image/webp")
    assert route.calls[0].request.url.params["size"] == "preview"
    respx.get(f"{BASE}/assets/g/thumbnail").mock(return_value=httpx.Response(404))
    with pytest.raises(AssetGone):
        client.thumbnail("g", "thumbnail")
    respx.get(f"{BASE}/assets/big/thumbnail").mock(
        return_value=httpx.Response(200, content=b"x" * 11, headers={"content-type": "image/png"})
    )
    with pytest.raises(ImmichError):
        client.thumbnail("big", "thumbnail", max_bytes=10)


def test_thumbnail_content_length_rejected_early(client: ImmichClient) -> None:
    respx.get(f"{BASE}/assets/big/thumbnail").mock(
        return_value=httpx.Response(
            200, content=b"x", headers={"content-type": "image/png", "content-length": "999"}
        )
    )
    with pytest.raises(ImmichError):
        client.thumbnail("big", "thumbnail", max_bytes=10)


def test_thumbnail_rejects_content_encoding_and_asks_identity(client: ImmichClient) -> None:
    route = respx.get(f"{BASE}/assets/z/thumbnail").mock(
        return_value=httpx.Response(
            200, content=b"x", headers={"content-type": "image/png", "content-encoding": "gzip"}
        )
    )
    with pytest.raises(ImmichError):
        client.thumbnail("z", "thumbnail")
    assert route.calls[0].request.headers["accept-encoding"] == "identity"


def test_restore_assets(client: ImmichClient) -> None:
    route = respx.post(f"{BASE}/trash/restore/assets").mock(
        return_value=httpx.Response(200, json={"count": 1})
    )
    client.restore_assets(["a1"])
    assert json.loads(route.calls[0].request.content) == {"ids": ["a1"]}
