"""Create the newspaper persistence schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001_newspaper"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_url"),
        schema="newspaper",
    )
    op.create_table(
        "editions",
        sa.Column("edition_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("epub_key", sa.Text(), nullable=True),
        sa.Column("epub_sha256", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "epub_sha256 ~ '^[0-9a-f]{64}$'", name="edition_checksum_hex"
        ),
        sa.CheckConstraint(
            "status <> 'validated' OR (epub_sha256 IS NOT NULL AND epub_key IS NOT NULL)",
            name="validated_edition_has_artifact",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'validated', 'failed')", name="edition_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edition_date"),
        schema="newspaper",
    )
    op.create_table(
        "editorial_runs",
        sa.Column("edition_date", sa.Date(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="running", nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=12, scale=6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="editorial_status"
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND estimated_cost_usd >= 0",
            name="editorial_usage_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_editorial_runs_edition_date"),
        "editorial_runs",
        ["edition_date"],
        unique=False,
        schema="newspaper",
    )
    op.create_table(
        "sources",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("licensing_note", sa.Text(), nullable=False),
        sa.Column("approval", sa.Text(), server_default="pending", nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "approval IN ('pending', 'approved', 'disabled')", name="source_approval"
        ),
        sa.CheckConstraint("kind IN ('rss', 'youtube')", name="source_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
        schema="newspaper",
    )
    op.create_table(
        "deliveries",
        sa.Column("edition_id", sa.Uuid(), nullable=False),
        sa.Column("destination_key", sa.Text(), nullable=False),
        sa.Column("epub_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "epub_sha256 ~ '^[0-9a-f]{64}$'", name="delivery_checksum_hex"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'smtp_accepted', 'ambiguous', 'failed')",
            name="delivery_status",
        ),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["newspaper.editions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edition_id", "destination_key"),
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_deliveries_available_at"),
        "deliveries",
        ["available_at"],
        unique=False,
        schema="newspaper",
    )
    op.create_table(
        "editorial_stories",
        sa.Column("editorial_run_id", sa.Uuid(), nullable=False),
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rank > 0", name="editorial_rank_positive"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["newspaper.articles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["editorial_run_id"],
            ["newspaper.editorial_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("editorial_run_id", "article_id"),
        sa.UniqueConstraint("editorial_run_id", "rank"),
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_editorial_stories_article_id"),
        "editorial_stories",
        ["article_id"],
        unique=False,
        schema="newspaper",
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="running", nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="ingestion_status"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["newspaper.sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "source_id"),
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_ingestion_runs_source_id"),
        "ingestion_runs",
        ["source_id"],
        unique=False,
        schema="newspaper",
    )
    op.create_table(
        "article_sources",
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("attributed_to", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["newspaper.articles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id", "source_id"],
            ["newspaper.ingestion_runs.id", "newspaper.ingestion_runs.source_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["newspaper.sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id"),
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_article_sources_article_id"),
        "article_sources",
        ["article_id"],
        unique=False,
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_article_sources_ingestion_run_id"),
        "article_sources",
        ["ingestion_run_id"],
        unique=False,
        schema="newspaper",
    )
    op.create_table(
        "delivery_attempts",
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "outcome", sa.Text(), server_default=sa.text("'started'"), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("smtp_message_id", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('started', 'smtp_accepted', 'ambiguous', 'failed')",
            name="delivery_attempt_outcome",
        ),
        sa.CheckConstraint("attempt_number > 0", name="delivery_attempt_positive"),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["newspaper.deliveries.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", "attempt_number"),
        schema="newspaper",
    )
    op.create_table(
        "edition_stories",
        sa.Column("edition_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position > 0", name="edition_position_positive"),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["newspaper.editions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["newspaper.editorial_stories.id"],
        ),
        sa.PrimaryKeyConstraint("edition_id", "story_id"),
        sa.UniqueConstraint("edition_id", "position"),
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_edition_stories_story_id"),
        "edition_stories",
        ["story_id"],
        unique=False,
        schema="newspaper",
    )
    op.create_table(
        "editorial_evidence",
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("article_source_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_source_id"],
            ["newspaper.article_sources.id"],
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["newspaper.editorial_stories.id"],
        ),
        sa.PrimaryKeyConstraint("story_id", "article_source_id"),
        schema="newspaper",
    )
    op.create_index(
        op.f("ix_newspaper_editorial_evidence_article_source_id"),
        "editorial_evidence",
        ["article_source_id"],
        unique=False,
        schema="newspaper",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON "
        "newspaper.ingestion_runs, newspaper.articles, newspaper.editorial_runs, "
        "newspaper.editorial_stories, newspaper.editions, newspaper.edition_stories, "
        "newspaper.deliveries, newspaper.delivery_attempts TO kastle_app"
    )
    op.execute(
        "GRANT SELECT, INSERT ON newspaper.article_sources, newspaper.editorial_evidence "
        "TO kastle_app"
    )
    op.execute(
        "GRANT SELECT, UPDATE (etag, last_modified) ON newspaper.sources TO kastle_app"
    )


def downgrade() -> None:
    op.drop_table("editorial_evidence", schema="newspaper")
    op.drop_table("edition_stories", schema="newspaper")
    op.drop_table("delivery_attempts", schema="newspaper")
    op.drop_table("article_sources", schema="newspaper")
    op.drop_table("ingestion_runs", schema="newspaper")
    op.drop_table("editorial_stories", schema="newspaper")
    op.drop_table("deliveries", schema="newspaper")
    op.drop_table("sources", schema="newspaper")
    op.drop_table("editorial_runs", schema="newspaper")
    op.drop_table("editions", schema="newspaper")
    op.drop_table("articles", schema="newspaper")
