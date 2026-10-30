import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from tests.pgsupport import BACKENDS

from app.auth.local import hash_password
from app.db.engine import make_sync_engine
from app.db.migrate import alembic_config

_settings = sa.table("settings", sa.column("key", sa.String), sa.column("value", sa.JSON))
_users = sa.table(
    "users",
    sa.column("sub", sa.String),
    sa.column("role", sa.String),
    sa.column("groups", sa.JSON),
    sa.column("disabled", sa.Boolean),
    sa.column("password_hash", sa.String),
)


@pytest.mark.parametrize("backend", BACKENDS)
def test_password_migration_roundtrip(
    backend: str, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    if backend == "pg":
        url = sync_url = request.getfixturevalue("pg_url")
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
        sync_url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = alembic_config(url)
    command.upgrade(cfg, "0006")
    h = hash_password("correct horse battery")
    eng = make_sync_engine(sync_url)
    try:
        with eng.begin() as c:
            c.execute(
                sa.insert(_settings).values(
                    key="local_admin", value={"username": "root", "password_hash": h}
                )
            )
            for sub, role in (("local:root", "admin"), ("oidc|1", "user")):
                c.execute(sa.insert(_users).values(sub=sub, role=role, groups=[], disabled=False))
        command.upgrade(cfg, "0007")
        with eng.begin() as c:
            rows = dict(c.execute(sa.select(_users.c.sub, _users.c.password_hash)).all())
            assert rows["local:root"] == h and rows["oidc|1"] is None
            flag = c.execute(sa.text("select must_change_password from users limit 1")).scalar()
            assert not flag
            # the user hash is now authoritative; a later password change must survive downgrade
            c.execute(
                sa.update(_users).where(_users.c.sub == "local:root").values(password_hash="new")
            )
        command.downgrade(cfg, "0006")
        with eng.begin() as c:
            val = c.execute(
                sa.select(_settings.c.value).where(_settings.c.key == "local_admin")
            ).scalar()
            val = json.loads(val) if isinstance(val, str) else val
            assert val == {"username": "root", "password_hash": "new"}
            assert "password_hash" not in {
                col["name"] for col in sa.inspect(c).get_columns("users")
            }
        command.upgrade(cfg, "head")
        with eng.begin() as c:
            got = c.execute(
                sa.select(_users.c.password_hash).where(_users.c.sub == "local:root")
            ).scalar()
            assert got == "new"
    finally:
        eng.dispose()
