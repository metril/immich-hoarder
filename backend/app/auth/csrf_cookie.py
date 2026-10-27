from http.cookies import SimpleCookie

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.deps import CSRF_COOKIE, SESSION_MAX_AGE


class CsrfCookieRenewal:
    """Keep the CSRF cookie as long-lived as the (sliding) session cookie.

    Re-sets the existing token with a fresh max_age on responses to authenticated
    sessions. It never mints a token: a missing cookie still fails the CSRF check.
    The Secure flag follows the request scheme (proxy headers via FORWARDED_ALLOW_IPS).
    Must sit inside SessionMiddleware so that scope["session"] is populated.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                token = self._token(scope)
                headers = MutableHeaders(scope=message)
                if token and not any(
                    v.startswith(f"{CSRF_COOKIE}=") for v in headers.getlist("set-cookie")
                ):
                    c: SimpleCookie = SimpleCookie()
                    c[CSRF_COOKIE] = token
                    c[CSRF_COOKIE]["path"] = "/"
                    c[CSRF_COOKIE]["max-age"] = str(SESSION_MAX_AGE)
                    c[CSRF_COOKIE]["samesite"] = "lax"
                    if scope.get("scheme") == "https":
                        c[CSRF_COOKIE]["secure"] = True
                    headers.append("set-cookie", c.output(header="").strip())
            await send(message)

        await self.app(scope, receive, wrapped)

    @staticmethod
    def _token(scope: Scope) -> str | None:
        session = scope.get("session")
        if not session or session.get("user_id") is None:
            return None
        raw = Headers(scope=scope).get("cookie", "")
        c: SimpleCookie = SimpleCookie()
        try:
            c.load(raw)
        except Exception:
            return None
        m = c.get(CSRF_COOKIE)
        return m.value if m and m.value else None


class SecureSessionCookie:
    """Add Secure to the session cookie on https requests (scheme-aware https_only)."""

    def __init__(self, app: ASGIApp, *, cookie: str = "session") -> None:
        self.app = app
        self.prefix = f"{cookie}="

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("scheme") != "https":
            await self.app(scope, receive, send)
            return

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                cookies = headers.getlist("set-cookie")
                if any(c.startswith(self.prefix) for c in cookies):
                    del headers["set-cookie"]
                    for c in cookies:
                        if c.startswith(self.prefix) and "secure" not in c.lower():
                            c += "; secure"
                        headers.append("set-cookie", c)
            await send(message)

        await self.app(scope, receive, wrapped)
