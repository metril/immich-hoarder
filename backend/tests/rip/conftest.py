import io
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image


def _img(fmt: str, color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, fmt)
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path.startswith("/redir/"):
            self.send_response(302)
            self.send_header("Location", parse_qs(u.query)["to"][0])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        base = f"http://{self.headers['Host']}"
        a = _img("JPEG", (200, 10, 10))
        pages = {
            "/page/dup": ("/img/a.jpg", "/img/a2.jpg"),
            "/page/two": ("/img/a.jpg", "/img/b.png"),
        }
        if u.path in pages:
            body = "\n".join(base + x for x in pages[u.path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        routes = {
            "/img/a.jpg": ("image/jpeg", a),
            "/img/a2.jpg": ("image/jpeg", a),
            "/img/corrupt.jpg": ("image/jpeg", a[:20] + b"garbage" * 5),
            "/img/b.png": ("image/png", _img("PNG", (10, 200, 10))),
            "/vid/c.mp4": ("video/mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64),
            "/html/fake.jpg": ("text/html", b"<html>not an image</html>"),
        }
        hit = routes.get(u.path)
        if hit is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", hit[0])
        self.send_header("Content-Length", str(len(hit[1])))
        self.end_headers()
        self.wfile.write(hit[1])

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def img_server() -> Iterator[str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()
    t.join()
