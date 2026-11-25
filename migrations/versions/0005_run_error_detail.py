"""Record per-story block reasons on editorial runs."""

import sqlalchemy as sa
from alembic import op

revision = "0005_run_error_detail"
down_revision = "0004_evidence_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("editorial_runs", sa.Column("error_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("editorial_runs", "error_detail")
