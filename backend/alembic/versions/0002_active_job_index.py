"""one active job per source

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHERE = sa.text("status IN ('queued','running')")


def upgrade() -> None:
    op.create_index(
        "uq_jobs_active_source",
        "jobs",
        ["source_id"],
        unique=True,
        sqlite_where=_WHERE,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_active_source", table_name="jobs")
