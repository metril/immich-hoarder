import gzip
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.main import create_app
from app.web.spa import CSP

INDEX = b"<!doctype html><title>app</title>"
JS = b"console.log('plain')"
JS_BR = b"BROTLI-BYTES"
JS_GZ = gzip.compress(JS)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_bytes(INDEX)
    (d / "favicon.svg").write_bytes(b"<svg/>")
    (d / "assets" / "app-abc123.js").write_bytes(JS)
    (d / "assets" / "app-abc123.js.br").write_bytes(JS_BR)
    (d / "assets" / "app-abc123.js.gz").write_bytes(JS_GZ)
    (tmp_path / "secret.txt").write_bytes(b"top-secret")
    return d


async def _client(settings: Settings, web_dir: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings.model_copy(update={"web_dir": web_dir}))
    app.state.runtime_enabled = False
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as c,
    ):
        yield c


@pytest.fixture
async def web(settings: Settings, dist: Path) -> AsyncIterator[httpx.AsyncClient]:
    async for c in _client(settings, dist):
        yield c


async def _raw(c: httpx.AsyncClient, path: str, **headers: str) -> tuple[httpx.Response, bytes]:
    req = c.build_request("GET", path, headers=headers)
    r = await c.send(req, stream=True)
    try:
        body = b"".join([chunk async for chunk in r.aiter_raw()])
    finally:
        await r.aclose()
    return r, body


def _secure(r: httpx.Response) -> None:
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"


def test_csp_value() -> None:
    assert "connect-src 'self'" in CSP
    assert "img-src 'self' data: blob:" in CSP
    assert "script-src 'self';" in CSP
    assert "script-src 'self' 'unsafe-inline'" not in CSP


async def test_index_no_cache_and_csp(web: httpx.AsyncClient) -> None:
    r = await web.get("/")
    assert r.status_code == 200
    assert r.content == INDEX
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["vary"] == "Accept-Encoding"
    _secure(r)


async def test_deep_link_fallback(web: httpx.AsyncClient) -> None:
    r = await web.get("/jobs/42")
    assert r.status_code == 200
    assert r.content == INDEX
    assert r.headers["cache-control"] == "no-cache"
    _secure(r)


async def test_asset_immutable(web: httpx.AsyncClient) -> None:
    r = await web.get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["content-type"] == "text/javascript; charset=utf-8"
    _secure(r)
    f = await web.get("/favicon.svg")
    assert f.headers["cache-control"] == "public, max-age=3600"
    assert f.headers["content-type"].startswith("image/svg+xml")


async def test_brotli_preferred_then_gzip_then_identity(web: httpx.AsyncClient) -> None:
    r, body = await _raw(web, "/assets/app-abc123.js", **{"Accept-Encoding": "gzip, br"})
    assert r.headers["content-encoding"] == "br"
    assert body == JS_BR
    assert r.headers["vary"] == "Accept-Encoding"
    assert r.headers["content-type"] == "text/javascript; charset=utf-8"
    r, body = await _raw(web, "/assets/app-abc123.js", **{"Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"
    assert body == JS_GZ
    r, body = await _raw(web, "/assets/app-abc123.js", **{"Accept-Encoding": "br;q=0, gzip"})
    assert r.headers["content-encoding"] == "gzip"
    r, body = await _raw(web, "/assets/app-abc123.js", **{"Accept-Encoding": "identity"})
    assert "content-encoding" not in r.headers
    assert body == JS
    assert r.headers["vary"] == "Accept-Encoding"


async def test_missing_asset_404_not_index(web: httpx.AsyncClient) -> None:
    r = await web.get("/assets/app-OLD999.js")
    assert r.status_code == 404
    assert b"<!doctype" not in r.content
    assert (await web.get("/nothing.js")).status_code == 404
    assert (await web.get("/assets/")).status_code == 404


async def test_api_unknown_is_json_404(web: httpx.AsyncClient) -> None:
    r = await web.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    r = await web.get("/api")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


async def test_health_ready_metrics_not_shadowed(web: httpx.AsyncClient) -> None:
    h = await web.get("/healthz")
    assert h.json() == {"status": "ok"}
    r = await web.get("/readyz")
    assert r.headers["content-type"].startswith("application/json")
    m = await web.get("/metrics")
    assert m.status_code == 401
    assert "html" not in m.headers["content-type"]


async def test_path_traversal_404(web: httpx.AsyncClient) -> None:
    for p in ("/..%2f..%2fsecret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt"):
        r = await web.get(p)
        assert b"top-secret" not in r.content
        assert r.status_code == 404, p


async def test_nul_byte_404(web: httpx.AsyncClient) -> None:
    r = await web.get("/a%00b")
    assert r.status_code == 404


async def test_symlink_escape_404(web: httpx.AsyncClient, dist: Path) -> None:
    (dist / "leak.txt").symlink_to(dist.parent / "secret.txt")
    r = await web.get("/leak.txt")
    assert r.status_code == 404
    assert b"top-secret" not in r.content


async def test_post_unknown_api_is_json_404_with_headers(web: httpx.AsyncClient) -> None:
    r = await web.post("/api/v1/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == CSP


async def test_post_non_api_is_405(web: httpx.AsyncClient) -> None:
    assert (await web.post("/jobs/1")).status_code == 405


async def test_api_get_404_has_security_headers(web: httpx.AsyncClient) -> None:
    _secure(await web.get("/api/v1/nope"))


async def test_api_docs_not_shadowed(web: httpx.AsyncClient) -> None:
    r = await web.get("/api/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()
    assert "content-security-policy" not in r.headers
    o = await web.get("/api/openapi.json")
    assert o.status_code == 200
    assert "content-security-policy" not in o.headers
    assert o.headers["x-content-type-options"] == "nosniff"


async def test_api_responses_get_nosniff_and_frame_ancestors(web: httpx.AsyncClient) -> None:
    r = await web.get("/api/v1/jobs")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == "frame-ancestors 'none'"


async def test_direct_precompressed_hit_404(web: httpx.AsyncClient) -> None:
    assert (await web.get("/assets/app-abc123.js.br")).status_code == 404
    assert (await web.get("/assets/app-abc123.js.gz")).status_code == 404


async def test_accept_encoding_star(web: httpx.AsyncClient) -> None:
    r, body = await _raw(web, "/assets/app-abc123.js", **{"Accept-Encoding": "*"})
    assert r.headers["content-encoding"] == "br"
    assert body == JS_BR
    r, body = await _raw(web, "/assets/app-abc123.js", **{"Accept-Encoding": "br;q=0, *"})
    assert r.headers["content-encoding"] == "gzip"


async def test_head_supported(web: httpx.AsyncClient) -> None:
    r = await web.head("/jobs/1")
    assert r.status_code == 200
    assert r.content == b""
    _secure(r)
    assert (await web.head("/assets/app-abc123.js")).status_code == 200


async def test_no_web_dir_api_only(settings: Settings, tmp_path: Path) -> None:
    async for c in _client(settings, tmp_path / "missing"):
        assert (await c.get("/healthz")).status_code == 200
        r = await c.get("/")
        assert r.status_code == 404
        assert r.json() == {"detail": "Not Found"}
