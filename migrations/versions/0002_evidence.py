"""Add evidence acquisition records for the drafting stage."""

import sqlalchemy as sa
from alembic import op

revision = "0002_evidence"
down_revision = "0001_newspaper"
branch_labels = None
depends_on = None

HEX64 = "length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'"


def upgrade() -> None:
    op.create_table(
        "evidence_acquisitions",
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('extracted', 'failed')", name="evidence_status"
        ),
        sa.CheckConstraint(
            f"content_sha256 IS NULL OR ({HEX64})",
            name="evidence_checksum_hex",
        ),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id"),
    )


def downgrade() -> None:
    op.drop_table("evidence_acquisitions")
