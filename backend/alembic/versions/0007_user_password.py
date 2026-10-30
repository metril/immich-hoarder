"""users.password_hash, users.must_change_password

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_settings = sa.table("settings", sa.column("key", sa.String), sa.column("value", sa.JSON))
_users = sa.table("users", sa.column("sub", sa.String), sa.column("password_hash", sa.String))


def _local_admin_setting() -> dict[str, str] | None:
    val = (
        op.get_bind()
        .execute(sa.select(_settings.c.value).where(_settings.c.key == "local_admin"))
        .scalar()
    )
    return val if isinstance(val, dict) and val.get("username") else None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    val = _local_admin_setting()
    if val and val.get("password_hash"):  # idempotent: never overwrites an existing hash
        op.get_bind().execute(
            sa.update(_users)
            .where(_users.c.sub == f"local:{val['username']}", _users.c.password_hash.is_(None))
            .values(password_hash=val["password_hash"])
        )


def downgrade() -> None:
    val = _local_admin_setting()
    if val:
        conn = op.get_bind()
        h = conn.execute(
            sa.select(_users.c.password_hash).where(_users.c.sub == f"local:{val['username']}")
        ).scalar()
        if h:  # the setting row stays; it just carries the current hash again
            conn.execute(
                sa.update(_settings)
                .where(_settings.c.key == "local_admin")
                .values(value={**val, "password_hash": h})
            )
    with op.batch_alter_table("users") as b:
        b.drop_column("must_change_password")
        b.drop_column("password_hash")
