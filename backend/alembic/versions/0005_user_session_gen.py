"""users.session_gen

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("session_gen", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("session_gen")
