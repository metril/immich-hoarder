import logging
import mimetypes
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.responses import FileResponse

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
    for part in header.split(","):
        m = _Q.match(part)
        if not m or m.group(1).lower() != coding:
            continue
        try:
            return float(m.group(2) if m.group(2) is not None else 1) > 0
        except ValueError:
            return False
    return False


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

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str, request: Request) -> Response:
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        accept = request.headers.get("accept-encoding", "")
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            return PlainTextResponse("Not Found", status_code=404, headers=_SECURITY)
        if target.is_file() and target.suffix not in (".br", ".gz"):
            cache = _IMMUTABLE if path.startswith("assets/") else _SHORT
            return _file(target, accept, cache)
        if path == "assets" or path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
            return PlainTextResponse("Not Found", status_code=404, headers=_SECURITY)
        return _file(root / "index.html", accept, "no-cache")
