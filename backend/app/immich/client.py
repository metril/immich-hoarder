import functools
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from app.immich.errors import AssetGone, ImmichAuthError, ImmichError, ImmichUnavailable

REQUIRED_PERMISSIONS = [
    "asset.upload",
    "asset.read",
    "asset.update",
    "asset.view",
    "album.read",
    "album.create",
    "albumAsset.create",
    "user.read",
]
DEVICE_ID = "immich-hoarder"
_RETRY_STATUSES = {429, 502, 503, 504}
_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
_BACKOFF = (0.5, 1.0, 2.0)
_RETRY_AFTER_CAP = 10.0


@dataclass(frozen=True)
class BulkResult:
    action: Literal["accept", "reject"]
    reason: str | None
    asset_id: str | None
    is_trashed: bool


@dataclass(frozen=True)
class UploadResult:
    asset_id: str
    duplicate: bool


@dataclass(frozen=True)
class AssetInfo:
    id: str
    is_trashed: bool


@dataclass(frozen=True)
class Album:
    id: str
    name: str
    asset_count: int


def _shaped[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Turn unparseable/unexpected 2xx bodies into ImmichError."""

    @functools.wraps(fn)
    def wrapper(*a: P.args, **kw: P.kwargs) -> R:
        try:
            return fn(*a, **kw)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            status = getattr(a[0], "_last_status", 200)
            raise ImmichError(status, "invalid response") from e

    return wrapper


def missing_permissions(perms: list[str]) -> list[str]:
    if "all" in perms:
        return []
    return [p for p in REQUIRED_PERMISSIONS if p not in perms]


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        msg = body.get("message") if isinstance(body, dict) else None
        if isinstance(msg, list):
            return "; ".join(str(m) for m in msg)
        if msg:
            return str(msg)
    except ValueError:
        pass
    return resp.text[:200]


class ImmichClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sleep = sleep
        self._last_status = 200
        self._send_device_fields = True
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/api",
            headers={"x-api-key": api_key},
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> "ImmichClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- transport -------------------------------------------------------
    def _send(
        self,
        do: Callable[[], httpx.Response],
        retry_statuses: frozenset[int] = frozenset(_RETRY_STATUSES),
    ) -> httpx.Response:
        last = len(_BACKOFF) - 1
        for attempt, backoff in enumerate(_BACKOFF):
            try:
                resp = do()
            except httpx.TransportError as e:
                if not isinstance(e, _CONNECT_ERRORS):
                    raise ImmichUnavailable(f"Immich request failed: {type(e).__name__}") from e
                if attempt == last:
                    raise ImmichUnavailable(f"Immich unreachable: {type(e).__name__}") from e
                self._sleep(backoff)
                continue
            if resp.status_code in retry_statuses:
                if attempt == last:
                    raise ImmichUnavailable(f"Immich unavailable (HTTP {resp.status_code})")
                delay = backoff
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        delay = min(max(float(ra), 0.0), _RETRY_AFTER_CAP)
                    except ValueError:
                        pass
                self._sleep(delay)
                continue
            self._last_status = resp.status_code
            return resp
        raise ImmichUnavailable("retries exhausted")  # pragma: no cover

    def _request(
        self,
        method: str,
        path: str,
        *,
        retry_statuses: frozenset[int] = frozenset(_RETRY_STATUSES),
        **kw: Any,
    ) -> httpx.Response:
        return self._send(lambda: self._http.request(method, path, **kw), retry_statuses)

    @staticmethod
    def _check(resp: httpx.Response) -> httpx.Response:
        if resp.is_success:
            return resp
        msg = _message(resp)
        if resp.status_code in (401, 403):
            raise ImmichAuthError(resp.status_code, msg)
        raise ImmichError(resp.status_code, msg)

    def _json(self, method: str, path: str, **kw: Any) -> Any:
        return self._check(self._request(method, path, **kw)).json()

    # -- API -------------------------------------------------------------
    def ping(self) -> bool:
        try:
            resp = self._request("GET", "/server/ping")
            return resp.is_success and resp.json().get("res") == "pong"
        except (ImmichUnavailable, ValueError, AttributeError):
            return False

    @_shaped
    def version(self) -> str:
        d = self._json("GET", "/server/version")
        return f"{d['major']}.{d['minor']}.{d['patch']}"

    @_shaped
    def key_permissions(self) -> list[str]:
        return [str(p) for p in self._json("GET", "/api-keys/me").get("permissions", [])]

    @_shaped
    def bulk_check(self, items: list[tuple[str, str]]) -> dict[str, BulkResult]:
        if not items:
            return {}
        body = {"assets": [{"id": i, "checksum": c} for i, c in items]}
        d = self._json("POST", "/assets/bulk-upload-check", json=body)
        return {
            r["id"]: BulkResult(
                action=r["action"],
                reason=r.get("reason"),
                asset_id=r.get("assetId"),
                is_trashed=bool(r.get("isTrashed", False)),
            )
            for r in d.get("results", [])
        }

    @_shaped
    def upload(
        self,
        path: Path,
        *,
        sha1hex: str,
        device_asset_id: str,
        file_created_at: datetime,
        file_modified_at: datetime,
        filename: str,
    ) -> UploadResult:
        def attempt(with_device: bool) -> httpx.Response:
            data = {
                "fileCreatedAt": _iso(file_created_at),
                "fileModifiedAt": _iso(file_modified_at),
                "filename": filename,
            }
            if with_device:
                data["deviceAssetId"] = device_asset_id
                data["deviceId"] = DEVICE_ID

            def do() -> httpx.Response:
                with path.open("rb") as fh:
                    return self._http.post(
                        "/assets",
                        data=data,
                        files={"assetData": (filename, fh, "application/octet-stream")},
                        headers={"x-immich-checksum": sha1hex},
                    )

            return self._send(do)

        resp = attempt(self._send_device_fields)
        if resp.status_code == 400 and self._send_device_fields:
            msg = _message(resp)
            if "deviceAssetId" in msg or "deviceId" in msg:
                self._send_device_fields = False
                resp = attempt(False)
        d = self._check(resp).json()
        return UploadResult(
            asset_id=d["id"], duplicate=resp.status_code == 200 or d.get("status") == "duplicate"
        )

    @_shaped
    def get_asset(self, asset_id: str) -> AssetInfo:
        resp = self._request("GET", f"/assets/{asset_id}")
        if resp.status_code in (400, 404):
            raise AssetGone(resp.status_code, _message(resp))
        d = self._check(resp).json()
        return AssetInfo(id=d["id"], is_trashed=bool(d.get("isTrashed", False)))

    @_shaped
    def list_albums(self) -> list[Album]:
        return [self._album(a) for a in self._json("GET", "/albums")]

    @_shaped
    def create_album(self, name: str) -> Album:
        # 502/504 may mean the album was created; only retry when it was surely not processed.
        resp = self._request(
            "POST", "/albums", json={"albumName": name}, retry_statuses=frozenset({429, 503})
        )
        if resp.status_code in (502, 504):
            raise ImmichUnavailable(f"Immich unavailable (HTTP {resp.status_code})")
        return self._album(self._check(resp).json())

    @staticmethod
    def _album(a: dict[str, Any]) -> Album:
        return Album(id=a["id"], name=a["albumName"], asset_count=int(a.get("assetCount", 0)))

    @_shaped
    def add_to_album(self, album_id: str, asset_ids: list[str]) -> dict[str, str | None]:
        d = self._json("PUT", f"/albums/{album_id}/assets", json={"ids": asset_ids})
        out: dict[str, str | None] = {}
        for r in d:
            err = r.get("error")
            out[r["id"]] = None if r.get("success") or err == "duplicate" else str(err or "unknown")
        return out

    def update_asset(
        self,
        asset_id: str,
        *,
        description: str | None,
        date_time_original: datetime | None,
    ) -> None:
        body: dict[str, str] = {}
        if description is not None:
            body["description"] = description
        if date_time_original is not None:
            body["dateTimeOriginal"] = _iso(date_time_original)
        if not body:
            return
        self._check(self._request("PUT", f"/assets/{asset_id}", json=body))
