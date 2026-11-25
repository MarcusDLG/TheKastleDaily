"""Persist the selection plan on each editorial run for the edition build."""

import sqlalchemy as sa
from alembic import op

revision = "0003_editorial_plan"
down_revision = "0002_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("editorial_runs", sa.Column("plan", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("editorial_runs", "plan")
