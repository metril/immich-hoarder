"""job status and (job_id, id) indexes

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_jobs_status", "jobs", ["status"])
    for t in ("job_events", "job_items"):
        op.drop_index(f"ix_{t}_job_id", table_name=t)
        op.create_index(f"ix_{t}_job_id_id", t, ["job_id", "id"])


def downgrade() -> None:
    for t in ("job_events", "job_items"):
        op.drop_index(f"ix_{t}_job_id_id", table_name=t)
        op.create_index(f"ix_{t}_job_id", t, ["job_id"])
    op.drop_index("ix_jobs_status", table_name="jobs")
