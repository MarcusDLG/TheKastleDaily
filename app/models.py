"""Persistence models for the newspaper workflow."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.database import SCHEMA


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Source(Record, Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("kind IN ('rss', 'youtube')", name="source_kind"),
        CheckConstraint(
            "approval IN ('pending', 'approved', 'disabled')", name="source_approval"
        ),
    )

    kind: Mapped[str] = mapped_column(Text)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    publisher: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    licensing_note: Mapped[str] = mapped_column(Text)
    approval: Mapped[str] = mapped_column(Text, server_default="pending")
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Record, Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("id", "source_id"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="ingestion_status"
        ),
    )

    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    status: Mapped[str] = mapped_column(Text, server_default="running")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)


class Article(Record, Base):
    __tablename__ = "articles"

    canonical_url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)


class ArticleSource(Record, Base):
    __tablename__ = "article_sources"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        ForeignKeyConstraint(
            ["ingestion_run_id", "source_id"], ["ingestion_runs.id", "ingestion_runs.source_id"]
        ),
    )

    article_id: Mapped[UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    ingestion_run_id: Mapped[UUID] = mapped_column(index=True)
    external_id: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    attributed_to: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EditorialRun(Record, Base):
    __tablename__ = "editorial_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="editorial_status"
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND estimated_cost_usd >= 0",
            name="editorial_usage_nonnegative",
        ),
    )

    edition_date: Mapped[date] = mapped_column(index=True)
    model: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="running")
    input_tokens: Mapped[int] = mapped_column(BigInteger, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, server_default="0")
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)


class EditorialStory(Record, Base):
    __tablename__ = "editorial_stories"
    __table_args__ = (
        UniqueConstraint("editorial_run_id", "article_id"),
        CheckConstraint("rank > 0", name="editorial_rank_positive"),
        UniqueConstraint("editorial_run_id", "rank"),
    )

    editorial_run_id: Mapped[UUID] = mapped_column(ForeignKey("editorial_runs.id"))
    article_id: Mapped[UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    rank: Mapped[int]
    category: Mapped[str] = mapped_column(Text)
    headline: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)


class EditorialEvidence(Base):
    __tablename__ = "editorial_evidence"

    story_id: Mapped[UUID] = mapped_column(ForeignKey("editorial_stories.id"), primary_key=True)
    article_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("article_sources.id"), primary_key=True, index=True
    )
    evidence_note: Mapped[str] = mapped_column(Text)


class Edition(Record, Base):
    __tablename__ = "editions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'validated', 'failed')", name="edition_status"),
        CheckConstraint("epub_sha256 ~ '^[0-9a-f]{64}$'", name="edition_checksum_hex"),
        CheckConstraint(
            "status <> 'validated' OR (epub_sha256 IS NOT NULL AND epub_key IS NOT NULL)",
            name="validated_edition_has_artifact",
        ),
    )

    # The scheduler will derive this date in America/New_York.
    edition_date: Mapped[date] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    epub_key: Mapped[str | None] = mapped_column(Text)
    epub_sha256: Mapped[str | None] = mapped_column(Text)


class EditionStory(Base):
    __tablename__ = "edition_stories"
    __table_args__ = (
        UniqueConstraint("edition_id", "position"),
        CheckConstraint("position > 0", name="edition_position_positive"),
    )

    edition_id: Mapped[UUID] = mapped_column(ForeignKey("editions.id"), primary_key=True)
    story_id: Mapped[UUID] = mapped_column(
        ForeignKey("editorial_stories.id"), primary_key=True, index=True
    )
    position: Mapped[int]


class Delivery(Record, Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("edition_id", "destination_key"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'smtp_accepted', 'ambiguous', 'failed')",
            name="delivery_status",
        ),
        CheckConstraint("epub_sha256 ~ '^[0-9a-f]{64}$'", name="delivery_checksum_hex"),
    )

    edition_id: Mapped[UUID] = mapped_column(ForeignKey("editions.id"))
    destination_key: Mapped[str] = mapped_column(Text)
    epub_sha256: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DeliveryAttempt(Record, Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("delivery_id", "attempt_number"),
        CheckConstraint("attempt_number > 0", name="delivery_attempt_positive"),
        CheckConstraint(
            "outcome IN ('started', 'smtp_accepted', 'ambiguous', 'failed')",
            name="delivery_attempt_outcome",
        ),
    )

    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("deliveries.id"))
    attempt_number: Mapped[int]
    outcome: Mapped[str] = mapped_column(Text, server_default=text("'started'"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    smtp_message_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
