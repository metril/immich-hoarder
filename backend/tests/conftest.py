import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from tests.pgsupport import PG_URL

from app.core.config import Settings
from app.db.engine import make_sync_engine
from app.main import create_app


@pytest.fixture
def pg_url() -> Iterator[str]:
    """A throwaway database on the IH_TEST_PG_URL server; dropped at teardown."""
    assert PG_URL
    name = f"ih_test_{uuid.uuid4().hex[:12]}"
    admin = make_sync_engine(PG_URL).execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(PG_URL).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        master_key=SecretStr("test-master-key-0123456789abcdef-xyz"),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
        public_url="http://testserver",
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    app.state.runtime_enabled = False
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as c,
    ):
        yield c
