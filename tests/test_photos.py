from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.build import build_edition
from app.drafting import run_drafting, to_render_drafts
from app.evidence import acquire, open_graph_image, store_photo
from app.models import (
    Article,
    ArticleSource,
    Base,
    EditorialRun,
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

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64
PAGE = b"""<html><head>
<meta property="og:image" content="https://cdn.example.com/lead.jpg">
<meta property="og:image:alt" content="Race leaders at turn four">
</head><body>story</body></html>"""


@pytest.fixture
def sessions():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def seed(session, category="motorsport", title="Fixture headline"):
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
        "edition_date": "2026-11-25",
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


def fetch_stub(body=PAGE):
    return lambda url: body


def extract_stub(text=EVIDENCE):
    return lambda body: text


def image_stub(payload=JPEG, fail=None):
    def fetch(url):
        if fail:
            raise fail
        return payload

    return fetch


def use_tmp_photos(monkeypatch, tmp_path):
    monkeypatch.setattr("app.evidence.photos_dir", lambda: tmp_path / "photos")


def test_open_graph_image_parses_meta_variants():
    page = b'<html><head><meta content="/img/lead.png" name="og:image"></head></html>'
    assert open_graph_image(page) == {"url": "/img/lead.png", "alt": None}


def test_open_graph_image_missing():
    assert open_graph_image(b"<html><head></head></html>") is None
    assert open_graph_image(b"<meta property='og:image' content=''>") is None


def test_store_photo_writes_content_addressed_file(tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    result = store_photo(
        "/lead.jpg", "https://example.com/story", fetch_image=image_stub()
    )
    assert result["url"] == "https://example.com/lead.jpg"
    stored = tmp_path / result["file"]
    assert stored.read_bytes() == JPEG
    again = store_photo("/lead.jpg", "https://example.com/other", fetch_image=image_stub())
    assert again["file"] == result["file"]


def test_store_photo_accepts_png(tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    result = store_photo(
        "diagram.png", "https://example.com/story", fetch_image=image_stub(PNG)
    )
    assert result["file"].endswith(".png")


def test_store_photo_rejects_non_image_and_failed_fetch(tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    assert store_photo(
        "x.jpg", "https://example.com/s", fetch_image=image_stub(b"<html>")
    ) is None
    assert store_photo(
        "x.jpg",
        "https://example.com/s",
        fetch_image=image_stub(fail=FeedError("response_too_large")),
    ) is None


def test_store_photo_rejects_http_url():
    # The real fetcher only allows HTTPS endpoints; no network is touched.
    assert store_photo("http://insecure.example.com/x.jpg", "https://example.com/s") is None


def test_acquire_stores_declared_photo(sessions, tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    with sessions() as session:
        article = seed(session)
        record = acquire(
            session,
            article,
            fetch=fetch_stub(),
            extract=extract_stub(),
            fetch_image=image_stub(),
        )
        assert record.status == "extracted"
        assert record.photo_url == "https://cdn.example.com/lead.jpg"
        assert record.photo_file.startswith("photos/")
        assert record.photo_alt == "Race leaders at turn four"
        assert (tmp_path / record.photo_file).read_bytes() == JPEG


def test_acquire_without_or_failed_photo_still_extracts(sessions, tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    with sessions() as session:
        plain = seed(session)
        record = acquire(
            session,
            plain,
            fetch=fetch_stub(b"<html>ok</html>"),
            extract=extract_stub(),
        )
        assert record.status == "extracted"
        assert record.photo_file is None

        broken = seed(session, title="Broken image story")
        record = acquire(
            session,
            broken,
            fetch=fetch_stub(),
            extract=extract_stub(),
            fetch_image=image_stub(fail=FeedError("http_404")),
        )
        assert record.status == "extracted"
        assert record.photo_file is None


def test_render_drafts_attach_photo_with_credit(sessions, tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    with sessions() as session:
        article = seed(session)
        run = run_drafting(
            session,
            plan_for((article, "motorsport", False)),
            fetch=fetch_stub(),
            extract=extract_stub(),
            fetch_image=image_stub(),
        )
        assert run["status"] == "drafted"
        drafts = to_render_drafts(
            session,
            session.scalar(
                select(EditorialRun.id).where(EditorialRun.status == "succeeded")
            ),
        )
        photo = drafts["stories"][0]["photo"]
        assert photo["file"].startswith("photos/")
        assert photo["alt"] == "Race leaders at turn four"
        assert photo["credit"] == "Image: Fixture Press"


def test_render_drafts_fall_back_to_headline_alt(sessions, tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    with sessions() as session:
        article = seed(session)
        page = b'<html><head><meta property="og:image" content="/lead.jpg"></head></html>'
        run = run_drafting(
            session,
            plan_for((article, "motorsport", False)),
            fetch=fetch_stub(page),
            extract=extract_stub(),
            fetch_image=image_stub(),
        )
        assert run["status"] == "drafted"
        drafts = to_render_drafts(
            session,
            session.scalar(
                select(EditorialRun.id).where(EditorialRun.status == "succeeded")
            ),
        )
        assert drafts["stories"][0]["photo"]["alt"] == "Fixture headline"


def test_build_embeds_acquired_photo(sessions, tmp_path, monkeypatch):
    use_tmp_photos(monkeypatch, tmp_path)
    with sessions() as session:
        other = seed(session, "motorsport", "Race report")
        reserved = seed(session, "sim_racing", "League recap")
        run = run_drafting(
            session,
            plan_for(
                (other, "motorsport", False),
                (reserved, "sim_racing", True),
            ),
            fetch=fetch_stub(),
            extract=extract_stub(),
            fetch_image=image_stub(),
        )
        assert run["status"] == "drafted"
        run = session.scalar(
            select(EditorialRun).where(EditorialRun.status == "succeeded")
        )

        result = build_edition(session, run, tmp_path)
        assert result["status"] == "validated"
        with ZipFile(tmp_path / "2026-11-25.epub") as archive:
            names = archive.namelist()
            assert "EPUB/photo-1.jpg" in names
            assert "EPUB/photo-2.jpg" in names
            story = archive.read("EPUB/story-1.xhtml").decode()
            assert "photo-1.jpg" in story
            assert "Race leaders at turn four" in story
            assert "Image: Fixture Press" in story
