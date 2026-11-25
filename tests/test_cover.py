import io
from collections import Counter
from datetime import UTC, date, datetime
from uuid import uuid4
from zipfile import ZipFile

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.build import build_edition
from app.cover import HEIGHT, WIDTH, render_cover
from app.drafting import run_drafting
from app.models import (
    Article,
    ArticleSource,
    Base,
    EditorialRun,
    IngestionRun,
    Source,
)

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


def seed(session, category, title):
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
            published_at=datetime(2026, 11, 24, 12, tzinfo=UTC),
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
                "timestamp": datetime(2026, 11, 24, 12, tzinfo=UTC),
                "reserved": reserved,
                "archived": False,
            }
            for article, category, reserved, *rest in entries
        ],
    }


def fetch_stub():
    return lambda url: b"<html>ok</html>"


def extract_stub(text=EVIDENCE):
    return lambda body: text


def test_render_cover_outputs_kindle_friendly_png(tmp_path):
    target = render_cover(EDITION_DATE, tmp_path / "cover.png")
    payload = target.read_bytes()
    assert len(payload) <= 4 * 1024 * 1024
    with Image.open(target) as image:
        assert image.format == "PNG"
        assert image.mode == "L"
        assert image.size == (WIDTH, HEIGHT)


def test_render_cover_is_deterministic(tmp_path):
    first = render_cover(EDITION_DATE, tmp_path / "a.png").read_bytes()
    second = render_cover(EDITION_DATE, tmp_path / "b.png").read_bytes()
    assert first == second
    other = render_cover(date(2026, 11, 26), tmp_path / "c.png").read_bytes()
    assert other != first


def test_render_cover_composites_lead_photo(tmp_path):
    lead = tmp_path / "lead.jpg"
    Image.linear_gradient("L").resize((900, 500)).save(lead, format="JPEG")
    with_photo = render_cover(
        EDITION_DATE,
        tmp_path / "with.png",
        photo=lead,
        caption="Race leaders at turn four",
    )
    without = render_cover(EDITION_DATE, tmp_path / "without.png")
    assert with_photo.read_bytes() != without.read_bytes()
    with Image.open(with_photo) as image:
        assert image.mode == "L"
        assert image.size == (WIDTH, HEIGHT)
        # The hero box carries photo ink, not the paper background.
        assert image.getpixel((WIDTH // 2, 960)) != 246


def test_render_cover_ignores_unreadable_photo(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not really a jpeg")
    target = render_cover(EDITION_DATE, tmp_path / "cover.png", photo=bad)
    assert (
        target.read_bytes()
        == render_cover(EDITION_DATE, tmp_path / "plain.png").read_bytes()
    )


def test_build_embeds_generated_cover(sessions, tmp_path):
    with sessions() as session:
        other = seed(session, "motorsport", "Race report")
        reserved = seed(session, "sim_racing", "League recap")
        result = run_drafting(
            session,
            plan_for(
                (other, "motorsport", False),
                (reserved, "sim_racing", True),
            ),
            fetch=fetch_stub(),
            extract=extract_stub(),
        )
        assert result["status"] == "drafted"
        run = session.scalar(
            select(EditorialRun).where(EditorialRun.status == "succeeded")
        )

        result = build_edition(session, run, tmp_path)
        assert result["status"] == "validated"
        assert (tmp_path / "cover-2026-11-25.png").exists()
        with ZipFile(tmp_path / "2026-11-25.epub") as archive:
            assert "EPUB/cover.png" in archive.namelist()
            package = archive.read("EPUB/package.opf").decode()
            assert 'properties="cover-image"' in package
            cover_page = archive.read("EPUB/cover.xhtml").decode()
            assert "cover.png" in cover_page


def test_build_puts_lead_story_photo_on_cover(sessions, tmp_path, monkeypatch):
    monkeypatch.setattr("app.evidence.photos_dir", lambda: tmp_path / "photos")
    jpeg = io.BytesIO()
    Image.linear_gradient("L").resize((640, 400)).save(jpeg, format="JPEG")
    page = (
        b'<html><head>'
        b'<meta property="og:image" content="https://cdn.example.com/lead.jpg">'
        b"</head><body>story</body></html>"
    )
    with sessions() as session:
        lead_story = seed(session, "motorsport", "Race report")
        other = seed(session, "sim_racing", "League recap")
        run_drafting(
            session,
            plan_for(
                (lead_story, "motorsport", False),
                (other, "sim_racing", True),
            ),
            fetch=lambda url: page,
            extract=extract_stub(),
            fetch_image=lambda url: jpeg.getvalue(),
        )
        run = session.scalar(
            select(EditorialRun).where(EditorialRun.status == "succeeded")
        )

        result = build_edition(session, run, tmp_path)
        assert result["status"] == "validated"
        with Image.open(tmp_path / "cover-2026-11-25.png") as image:
            assert image.getpixel((WIDTH // 2, 960)) != 246
