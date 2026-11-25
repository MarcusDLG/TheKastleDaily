"""Record story photo acquisitions on evidence records."""

import sqlalchemy as sa
from alembic import op

revision = "0004_evidence_photos"
down_revision = "0003_editorial_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_acquisitions", sa.Column("photo_url", sa.Text(), nullable=True))
    op.add_column("evidence_acquisitions", sa.Column("photo_file", sa.Text(), nullable=True))
    op.add_column("evidence_acquisitions", sa.Column("photo_alt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_acquisitions", "photo_alt")
    op.drop_column("evidence_acquisitions", "photo_file")
    op.drop_column("evidence_acquisitions", "photo_url")
