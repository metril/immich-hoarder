import logging
import mimetypes
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.responses import FileResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger(__name__)

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)
_SECURITY = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}
_TYPES = {".js": "text/javascript; charset=utf-8", ".webmanifest": "application/manifest+json"}
_IMMUTABLE = "public, max-age=31536000, immutable"
_SHORT = "public, max-age=3600"
_Q = re.compile(r"^\s*([^;\s]+)\s*(?:;\s*q\s*=\s*([0-9.]+))?\s*$", re.I)


def _accepts(header: str, coding: str) -> bool:
    star: bool | None = None
    for part in header.split(","):
        m = _Q.match(part)
        if not m:
            continue
        name = m.group(1).lower()
        if name != coding and name != "*":
            continue
        try:
            ok = float(m.group(2) if m.group(2) is not None else 1) > 0
        except ValueError:
            ok = False
        if name == coding:
            return ok
        star = ok
    return bool(star)


_NO_CSP = ("/api/docs", "/api/openapi.json")


class ApiHeaders:
    """nosniff + frame-ancestors on /api/* responses (not overriding existing headers)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/api" or path.startswith("/api/")):
            await self.app(scope, receive, send)
            return
        csp = path not in _NO_CSP

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                have = {k.lower() for k, _ in headers}
                if b"x-content-type-options" not in have:
                    headers.append((b"x-content-type-options", b"nosniff"))
                if csp and b"content-security-policy" not in have:
                    headers.append((b"content-security-policy", b"frame-ancestors 'none'"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, wrapped)


def _media_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return _TYPES.get(suffix) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def _file(path: Path, accept: str, cache: str) -> Response:
    headers = {**_SECURITY, "Vary": "Accept-Encoding", "Cache-Control": cache}
    served = path
    for coding, ext in (("br", ".br"), ("gzip", ".gz")):
        sibling = path.with_name(path.name + ext)
        if _accepts(accept, coding) and sibling.is_file():
            served = sibling
            headers["Content-Encoding"] = coding
            break
    return FileResponse(served, media_type=_media_type(path.name), headers=headers)


def mount_spa(app: FastAPI, web_dir: Path) -> None:
    index = web_dir / "index.html"
    if not index.is_file():
        log.info("web_dir %s has no index.html; serving API only", web_dir)
        return
    root = web_dir.resolve()

    def api_404() -> Response:
        return JSONResponse({"detail": "Not Found"}, status_code=404, headers=_SECURITY)

    all_methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

    @app.api_route("/api", methods=all_methods, include_in_schema=False)
    @app.api_route("/api/{rest:path}", methods=all_methods, include_in_schema=False)
    async def api_unknown(request: Request) -> Response:
        return api_404()

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str, request: Request) -> Response:
        if path == "api" or path.startswith("api/"):
            return api_404()
        accept = request.headers.get("accept-encoding", "")
        not_found = PlainTextResponse("Not Found", status_code=404, headers=_SECURITY)
        if any(seg.startswith(".") for seg in path.split("/")):
            return not_found
        try:
            target = (root / path).resolve()
            is_file = target.is_file()
        except (ValueError, OSError):
            return not_found
        if not target.is_relative_to(root):
            return not_found
        rel = target.relative_to(root).as_posix()
        if is_file and target.suffix not in (".br", ".gz"):
            return _file(target, accept, _IMMUTABLE if rel.startswith("assets/") else _SHORT)
        if path == "assets" or path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
            return not_found
        return _file(root / "index.html", accept, "no-cache")
