import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.build import build_edition, latest_succeeded_run
from app.drafting import run_drafting
from app.models import (
    Article,
    ArticleSource,
    Base,
    Edition,
    EditionStory,
    EditorialRun,
    EditorialStory,
    IngestionRun,
    Source,
)
from app.rss import FeedError

EVIDENCE = (
    "Engineers shipped a new relay protocol after three years of field "
    "testing across four continents and dozens of production networks.\n\n"
    "The maintainers described the rollout as cautious, citing earlier "
    "incidents where premature changes caused several days of downtime.\n\n"
    "Community feedback will decide whether the older relay mode is retired "
    "before the next major release is tagged later this spring."
)

EDITION_DATE = date(2026, 11, 25)


@pytest.fixture
def sessions():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def seed(session, category, title, stamp=None):
    source = Source(
        kind="rss",
        endpoint=f"https://example.com/feed-{uuid4().hex[:8]}",
        publisher="Fixture Press",
        category=category,
        approval="approved",
        licensing_note="Fixture",
    )
    session.add(source)
    session.flush()
    ingest = IngestionRun(source_id=source.id, status="succeeded")
    session.add(ingest)
    session.flush()
    article = Article(
        canonical_url=f"https://example.com/{uuid4().hex[:8]}", title=title
    )
    session.add(article)
    session.flush()
    session.add(
        ArticleSource(
            article_id=article.id,
            source_id=source.id,
            ingestion_run_id=ingest.id,
            external_id=uuid4().hex[:8],
            source_url=article.canonical_url,
            attributed_to="Fixture Press",
            published_at=stamp or datetime(2026, 11, 24, 12, tzinfo=UTC),
        )
    )
    session.flush()
    return article


def plan_for(*entries):
    """entries: (article, category, reserved) tuples in plan order."""
    counts = Counter(category for _, category, *rest in entries)
    return {
        "edition_date": EDITION_DATE.isoformat(),
        "target": len(entries),
        "coverage_floor_met": any(entry[2] for entry in entries),
        "coverage": {
            category: {"target": count, "selected": count}
            for category, count in counts.items()
        },
        "stories": [
            {
                "article_id": article.id,
                "provenance_id": uuid4(),
                "title": article.title,
                "url": article.canonical_url,
                "publisher": "Fixture Press",
                "category": category,
                "timestamp": stamp[0] if stamp else datetime(2026, 11, 24, 12, tzinfo=UTC),
                "reserved": reserved,
                "archived": False,
            }
            for article, category, reserved, *stamp in entries
        ],
    }


def fetch_stub(deny=()):
    def fetch(url):
        if url in deny:
            raise FeedError("http_403")
        return b"<html>ok</html>"

    return fetch


def extract_stub(text=EVIDENCE):
    return lambda body: text


def draft(session, plan, deny=()):
    result = run_drafting(
        session, plan, fetch=fetch_stub(deny), extract=extract_stub()
    )
    assert result["status"] == "drafted"
    return session.scalar(
        select(EditorialRun).where(EditorialRun.status == "succeeded")
    )


def story_positions(session, edition_id):
    rows = session.scalars(
        select(EditionStory)
        .where(EditionStory.edition_id == edition_id)
        .order_by(EditionStory.position)
    ).all()
    return rows


def test_build_records_validated_edition(sessions, tmp_path):
    with sessions() as session:
        other = seed(session, "motorsport", "Race report")
        reserved = seed(session, "sim_racing", "League recap")
        run = draft(
            session,
            plan_for(
                (other, "motorsport", False),
                (reserved, "sim_racing", True),
            ),
        )
        assert json.loads(run.plan)["edition_date"] == EDITION_DATE.isoformat()

        result = build_edition(session, run, tmp_path)
        assert result["status"] == "validated"
        assert result["stories"] == 2

        target = tmp_path / "2026-11-25.epub"
        assert result["epub_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        edition = session.scalar(select(Edition))
        assert edition.edition_date == EDITION_DATE
        assert edition.status == "validated"
        assert edition.epub_key == str(target)
        assert edition.epub_sha256 == result["epub_sha256"]

        positions = story_positions(session, edition.id)
        expected = {
            article.id: session.scalar(
                select(EditorialStory.id).where(EditorialStory.article_id == article.id)
            )
            for article in (other, reserved)
        }
        assert [row.story_id for row in positions] == [
            expected[other.id],
            expected[reserved.id],
        ]

        with ZipFile(target) as book:
            spine_names = {
                name for name in book.namelist() if name.startswith("EPUB/story-")
            }
        assert spine_names == {"EPUB/story-1.xhtml", "EPUB/story-2.xhtml"}


def test_build_is_idempotent(sessions, tmp_path):
    with sessions() as session:
        article = seed(session, "sim_racing", "League recap")
        run = draft(session, plan_for((article, "sim_racing", True)))
        first = build_edition(session, run, tmp_path)
        before = (tmp_path / "2026-11-25.epub").read_bytes()

        again = build_edition(session, run, tmp_path)
        assert again["status"] == "already_validated"
        assert again["epub_sha256"] == first["epub_sha256"]
        assert (tmp_path / "2026-11-25.epub").read_bytes() == before
        assert len(session.scalars(select(Edition)).all()) == 1


def test_reserve_flag_moves_to_surviving_story(sessions, tmp_path):
    with sessions() as session:
        other = seed(session, "motorsport", "Race report")
        pick = seed(
            session,
            "sim_racing",
            "Original pick",
            stamp=datetime(2026, 11, 24, 18, tzinfo=UTC),
        )
        spare = seed(
            session,
            "sim_racing",
            "Spare story",
            stamp=datetime(2026, 11, 24, 9, tzinfo=UTC),
        )
        plan = plan_for(
            (other, "motorsport", False),
            (pick, "sim_racing", True, datetime(2026, 11, 24, 18, tzinfo=UTC)),
            (spare, "sim_racing", False, datetime(2026, 11, 24, 9, tzinfo=UTC)),
        )
        run = draft(session, plan, deny={pick.canonical_url})

        result = build_edition(session, run, tmp_path)
        assert result["status"] == "validated"
        assert result["stories"] == 2
        edition = session.scalar(select(Edition))
        positions = story_positions(session, edition.id)
        story_ids = {
            session.scalar(
                select(EditorialStory.article_id).where(
                    EditorialStory.id == row.story_id
                )
            )
            for row in positions
        }
        assert story_ids == {other.id, spare.id}


def test_losing_the_reserved_story_fails_the_build(sessions, tmp_path):
    with sessions() as session:
        reserved = seed(session, "sim_racing", "League recap")
        other = seed(session, "motorsport", "Race report")
        run = draft(
            session,
            plan_for(
                (other, "motorsport", False),
                (reserved, "sim_racing", True),
            ),
            deny={reserved.canonical_url},
        )

        result = build_edition(session, run, tmp_path)
        assert result["status"] == "failed"
        assert "reserved" in result["error"]
        assert session.scalar(select(Edition)).status == "failed"
        assert not (tmp_path / "2026-11-25.epub").exists()
        assert not list(tmp_path.glob(".*.tmp"))


def test_failed_build_recovers_on_retry(sessions, tmp_path):
    with sessions() as session:
        article = seed(session, "sim_racing", "League recap")
        run = draft(session, plan_for((article, "sim_racing", True)))
        run.plan = None
        session.flush()

        failed = build_edition(session, run, tmp_path)
        assert failed["status"] == "failed"
        assert "selection plan" in failed["error"]

        plan = plan_for((article, "sim_racing", True))
        run.plan = json.dumps(plan, sort_keys=True, default=str)
        session.flush()
        recovered = build_edition(session, run, tmp_path)
        assert recovered["status"] == "validated"
        assert recovered["edition_id"] == failed["edition_id"]
        assert session.scalar(select(Edition)).status == "validated"
        assert (tmp_path / "2026-11-25.epub").exists()


def test_all_blocked_stories_fail_the_build(sessions, tmp_path):
    with sessions() as session:
        article = seed(session, "sim_racing", "League recap")
        run = draft(
            session,
            plan_for((article, "sim_racing", True)),
            deny={article.canonical_url},
        )
        result = build_edition(session, run, tmp_path)
        assert result["status"] == "failed"
        assert "No drafted stories" in result["error"]


def test_latest_succeeded_run_ignores_failed_runs(sessions):
    with sessions() as session:
        session.add(
            EditorialRun(
                edition_date=EDITION_DATE,
                model="mock",
                status="failed",
                finished_at=datetime(2026, 11, 25, 8, tzinfo=UTC),
            )
        )
        article = seed(session, "sim_racing", "League recap")
        run = draft(session, plan_for((article, "sim_racing", True)))
        assert latest_succeeded_run(session, EDITION_DATE).id == run.id
        assert latest_succeeded_run(session, date(2026, 11, 26)) is None
