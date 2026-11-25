"""Persistence models for the newspaper workflow.

SQLite storage: datetimes are naive UTC on disk and timezone-aware UTC in
Python (UTCDateTime below). Hex artifact checksums are enforced by length
plus a no-nonhex-characters GLOB check.
"""

import uuid
from datetime import UTC, date, datetime
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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Naive-UTC storage that always returns timezone-aware UTC values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires timezone-aware values")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def _hex64(column):
    return f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'"


HEX64 = _hex64("epub_sha256")


class Base(DeclarativeBase):
    metadata = MetaData()


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC)
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
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
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
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


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
    plan: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="running")
    input_tokens: Mapped[int] = mapped_column(BigInteger, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, server_default="0")
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0")
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
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


class EvidenceAcquisition(Record, Base):
    __tablename__ = "evidence_acquisitions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('extracted', 'failed')", name="evidence_status"
        ),
        CheckConstraint(
            f"content_sha256 IS NULL OR ({_hex64('content_sha256')})",
            name="evidence_checksum_hex",
        ),
    )

    article_id: Mapped[UUID] = mapped_column(
        ForeignKey("articles.id"), unique=True
    )
    url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    photo_file: Mapped[str | None] = mapped_column(Text)
    photo_alt: Mapped[str | None] = mapped_column(Text)


class Edition(Record, Base):
    __tablename__ = "editions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'validated', 'failed')", name="edition_status"),
        CheckConstraint(f"epub_sha256 IS NULL OR ({HEX64})", name="edition_checksum_hex"),
        CheckConstraint(
            "status <> 'validated' OR (epub_sha256 IS NOT NULL AND epub_key IS NOT NULL)",
            name="validated_edition_has_artifact",
        ),
    )

    # The scheduler derives this date in America/New_York.
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
        CheckConstraint(HEX64, name="delivery_checksum_hex"),
    )

    edition_id: Mapped[UUID] = mapped_column(ForeignKey("editions.id"))
    destination_key: Mapped[str] = mapped_column(Text)
    epub_sha256: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    available_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), index=True
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
    outcome: Mapped[str] = mapped_column(Text, server_default="started")
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    smtp_message_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
