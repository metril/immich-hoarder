"""Test-only server for the Playwright/Lighthouse runs: real app, built bundle, auto-login.

Lives under backend/tests/, which .dockerignore excludes, so the bypass never ships.
"""

import asyncio
import base64
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from itsdangerous import TimestampSigner
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.db.engine import make_engine
from app.db.migrate import upgrade_head_async
from app.db.models import (
    ImmichTarget,
    Job,
    JobEvent,
    JobItem,
    JobStatus,
    Role,
    Source,
    User,
)
from app.main import create_app

SESSION_SECRET = "e2e-session-secret-0123456789abcdef"
PORT = int(os.environ.get("E2E_PORT", "8090"))
CSRF = "e2e"


class AutoLogin:
    """Injects the session + CSRF cookies on requests that lack them (outside SessionMiddleware)."""

    def __init__(self, app: ASGIApp, session_value: str) -> None:
        self.app = app
        self.session_value = session_value

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = list(scope["headers"])
        have = b"; ".join(v for k, v in headers if k == b"cookie").decode("latin-1")
        names = {c.split("=", 1)[0].strip() for c in have.split(";") if c}
        extra = []
        if "session" not in names:
            extra.append(f"session={self.session_value}")
        if "ih_csrf" not in names:
            extra.append(f"ih_csrf={CSRF}")
        if not extra:
            await self.app(scope, receive, send)
            return
        cookie = "; ".join([c for c in (have, *extra) if c])
        headers = [(k, v) for k, v in headers if k != b"cookie"]
        headers.append((b"cookie", cookie.encode("latin-1")))
        scope = {**scope, "headers": headers}

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                out = list(message.get("headers", []))
                for c in extra:
                    out.append((b"set-cookie", f"{c}; Path=/; SameSite=Lax".encode()))
                message = {**message, "headers": out}
            await send(message)

        await self.app(scope, receive, wrapped)


def _session_cookie(user_id: int) -> str:
    # Same encoding as Starlette's SessionMiddleware.
    data = base64.b64encode(json.dumps({"user_id": user_id}).encode("utf-8"))
    return TimestampSigner(SESSION_SECRET).sign(data).decode("utf-8")


async def _seed(settings: Settings) -> int:
    await upgrade_head_async(settings.database_url)
    engine = make_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    async with sf() as s, s.begin():
        admin = User(
            sub="local:e2e-admin",  # local accounts need no OIDC group mapping
            email="e2e@example.test",
            name="E2E Admin",
            role=Role.admin,
            groups=[],
        )
        s.add(admin)
        await s.flush()
        target = ImmichTarget(
            name="E2E Immich", url="http://immich.invalid", api_key_enc=b"x", owner_id=admin.id
        )
        s.add(target)
        await s.flush()
        source = Source(
            name="E2E source",
            url="https://example.test/gallery",
            extractor="gallery-dl",
            target_id=target.id,
            owner_id=admin.id,
            enabled=False,
        )
        s.add(source)
        await s.flush()
        job = Job(
            source_id=source.id,
            triggered_by=admin.id,
            status=JobStatus.succeeded,
            counters={"uploaded": 2, "skipped": 1},
            started_at=now,
            finished_at=now,
        )
        s.add(job)
        await s.flush()
        for i, outcome in enumerate(("uploaded", "uploaded", "skipped")):
            s.add(
                JobItem(
                    job_id=job.id,
                    url=f"https://example.test/gallery/{i}.jpg",
                    outcome=outcome,
                    reason="duplicate" if outcome == "skipped" else None,
                )
            )
        for i in range(5):
            s.add(
                JobEvent(
                    job_id=job.id,
                    ts=now,
                    level="info",
                    type="log",
                    data={"type": "log", "msg": f"e2e log line {i}", "logger": "e2e"},
                )
            )
        long_name = "Extremely long source name for truncation checks " * 3
        long_url = "https://example.test/very/long/path/" + "segment-" * 30 + "end.jpg"
        for i in range(3):
            s.add(
                Source(
                    name=f"{long_name}{i}",
                    url=long_url,
                    extractor="gallery-dl",
                    target_id=target.id,
                    owner_id=admin.id,
                    enabled=True,
                )
            )
        s.add(
            ImmichTarget(
                name="Target with an exceptionally long display name " * 3,
                url="http://immich-server-with-a-very-long-hostname." + "sub." * 12 + "invalid",
                api_key_enc=b"x",
                owner_id=admin.id,
            )
        )
        for i in range(2):
            s.add(
                User(
                    sub=f"e2e-long-{i}",
                    email=f"a.very.long.email.address.for.truncation.{i}@subdomain.example-company.test",
                    name="Maximilian Alexander Bartholomew Montgomery-Featherstonehaugh " * 2,
                    role=Role.user if i else Role.admin,
                    groups=["admins"],
                )
            )
        s.add(
            JobItem(
                job_id=job.id,
                url=long_url,
                outcome="failed",
                reason="Upstream error " + "with a long explanatory reason " * 6,
            )
        )
        admin_id = admin.id
    await engine.dispose()
    return admin_id


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="ih-e2e-"))
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{root / 'e2e.db'}",
        master_key=SecretStr("e2e-master-key-0123456789abcdef-xyz"),
        session_secret=SecretStr(SESSION_SECRET),
        scratch_dir=root / "scratch",
        backup_dir=root / "backups",
        web_dir=Path(__file__).resolve().parents[2] / "frontend" / "dist",
    )
    settings.scratch_dir.mkdir()
    settings.backup_dir.mkdir()
    admin_id = asyncio.run(_seed(settings))
    app = create_app(settings)
    uvicorn.run(
        AutoLogin(app, _session_cookie(admin_id)),  # type: ignore[arg-type]
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
        lifespan="on",
    )


if __name__ == "__main__":
    main()
