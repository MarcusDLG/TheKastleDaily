import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models import (
    Article,
    ArticleSource,
    Base,
    Delivery,
    DeliveryAttempt,
    Edition,
    EditionStory,
    EditorialEvidence,
    EditorialRun,
    EditorialStory,
    EvidenceAcquisition,
    IngestionRun,
    Source,
)
from app.retention import prune

OLD = datetime.now(UTC) - timedelta(days=45)
FRESH = datetime.now(UTC) - timedelta(days=3)
SHA = "a" * 64


@pytest.fixture
def sessions():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def seed_chain(session, stamp, title, edition_day):
    """One full row graph: source→ingest→article→acquisition→run→story→
    evidence→edition→edition_story→delivery→attempt."""
    source = Source(
        kind="rss",
        endpoint=f"https://example.com/feed-{uuid4().hex[:8]}",
        publisher="Fixture Press",
        category="motorsport",
        approval="approved",
        licensing_note="Fixture",
        created_at=stamp,
    )
    session.add(source)
    session.flush()
    ingest = IngestionRun(
        source_id=source.id, status="succeeded", created_at=stamp
    )
    session.add(ingest)
    session.flush()
    article = Article(
        canonical_url=f"https://example.com/{uuid4().hex[:8]}",
        title=title,
        created_at=stamp,
    )
    session.add(article)
    session.flush()
    article_source = ArticleSource(
        article_id=article.id,
        source_id=source.id,
        ingestion_run_id=ingest.id,
        external_id=uuid4().hex[:8],
        source_url=article.canonical_url,
        attributed_to="Fixture Press",
        published_at=datetime(2026, 11, 24, 12, tzinfo=UTC),
        created_at=stamp,
    )
    session.add(article_source)
    acquisition = EvidenceAcquisition(
        article_id=article.id,
        url=article.canonical_url,
        fetched_at=stamp,
        status="extracted",
        extracted_text="evidence",
        created_at=stamp,
    )
    session.add(acquisition)
    run = EditorialRun(
        edition_date=edition_day,
        model="openai/gpt-5-mini",
        status="succeeded",
        created_at=stamp,
    )
    session.add(run)
    session.flush()
    story = EditorialStory(
        editorial_run_id=run.id,
        article_id=article.id,
        rank=1,
        category="motorsport",
        headline=title,
        body="body",
        created_at=stamp,
    )
    session.add(story)
    session.flush()
    session.add(
        EditorialEvidence(
            story_id=story.id,
            article_source_id=article_source.id,
            evidence_note="note",
        )
    )
    edition = Edition(
        edition_date=edition_day,
        status="validated",
        epub_key="/x.epub",
        epub_sha256=SHA,
        created_at=stamp,
    )
    session.add(edition)
    session.flush()
    session.add(
        EditionStory(edition_id=edition.id, story_id=story.id, position=1)
    )
    delivery = Delivery(
        edition_id=edition.id,
        destination_key="kindle@example.com",
        epub_sha256=SHA,
        status="smtp_accepted",
        created_at=stamp,
    )
    session.add(delivery)
    session.flush()
    session.add(
        DeliveryAttempt(
            delivery_id=delivery.id,
            attempt_number=1,
            outcome="smtp_accepted",
            created_at=stamp,
        )
    )
    session.flush()
    return source


def counts(session):
    tables = (
        Article,
        ArticleSource,
        Delivery,
        DeliveryAttempt,
        Edition,
        EditionStory,
        EditorialEvidence,
        EditorialRun,
        EditorialStory,
        EvidenceAcquisition,
        IngestionRun,
    )
    return {
        table.__tablename__: session.scalar(
            select(func.count()).select_from(table)
        )
        for table in tables
    }


def test_prune_removes_expired_rows_and_keeps_recent(sessions):
    with sessions() as session:
        seed_chain(session, OLD, "Old story", date(2026, 10, 11))
        seed_chain(session, FRESH, "Fresh story", date(2026, 11, 22))

        result = prune(session, "/nonexistent-dir")
        session.commit()

        remaining = counts(session)
        for table in (
            "articles",
            "article_sources",
            "evidence_acquisitions",
            "editorial_runs",
            "editorial_stories",
            "editorial_evidence",
            "editions",
            "edition_stories",
            "deliveries",
            "delivery_attempts",
            "ingestion_runs",
        ):
            assert remaining[table] == 1, table
        # The feed registry is configuration — both sources stay.
        assert session.scalar(select(func.count()).select_from(Source)) == 2
        assert result["articles"] == 1
        assert result["edition_stories"] == 1
        assert result["editorial_evidence"] == 1
        assert result["status"] == "pruned"


def test_prune_removes_old_artifacts_only(sessions, tmp_path):
    old_epub = tmp_path / "2026-10-01.epub"
    fresh_epub = tmp_path / "2026-11-24.epub"
    old_cover = tmp_path / "cover-2026-10-01.png"
    photos = tmp_path / "photos"
    photos.mkdir()
    old_photo = photos / "aaa.jpg"
    for path in (old_epub, fresh_epub, old_cover, old_photo):
        path.write_bytes(b"x")
    stale = (datetime.now(UTC) - timedelta(days=45)).timestamp()
    os.utime(old_epub, (stale, stale))
    os.utime(old_cover, (stale, stale))
    os.utime(old_photo, (stale, stale))

    with sessions() as session:
        result = prune(session, tmp_path)

    assert result["files_removed"] == 3
    assert not old_epub.exists()
    assert not old_cover.exists()
    assert not old_photo.exists()
    assert fresh_epub.exists()
