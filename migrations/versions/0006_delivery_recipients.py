"""Add the delivery recipient registry.

Addresses are additive from KINDLE_ADDRESS on every pipeline pass;
the admin surface owns enable/disable from then on.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_delivery_recipients"
down_revision = "0005_run_error_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_recipients",
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("address"),
    )


def downgrade() -> None:
    op.drop_table("delivery_recipients")
