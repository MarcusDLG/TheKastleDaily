import json
import threading
import urllib.request
from datetime import UTC, date, datetime
from http.server import ThreadingHTTPServer
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin import dashboard_data, make_handler, render_html
from app.models import (
    Article,
    Base,
    Delivery,
    Edition,
    EditionStory,
    EditorialRun,
    EditorialStory,
    IngestionRun,
    Source,
)

SHA = "b" * 64


@pytest.fixture
def sessions():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def seed_dashboard(session):
    """One source + ingest, one run with a blocked story, one edition,
    one edition_story, one delivery."""
    source = Source(
        kind="rss",
        endpoint=f"https://feeds.example.com/{uuid4().hex[:8]}",
        publisher="<script>alert(1)</script> Gazette",
        category="technology_ai",
        approval="approved",
        licensing_note="Fixture",
    )
    session.add(source)
    session.flush()
    session.add(
        IngestionRun(
            source_id=source.id,
            status="failed",
            error_code="http_403",
            finished_at=datetime.now(UTC),
        )
    )
    session.add(
        IngestionRun(source_id=source.id, status="succeeded",
                     finished_at=datetime.now(UTC))
    )
    article = Article(
        canonical_url=f"https://example.com/{uuid4().hex[:8]}",
        title="Fixture headline",
    )
    session.add(article)
    session.flush()
    run = EditorialRun(
        edition_date=date(2026, 11, 25),
        model="openai/gpt-5-mini",
        status="succeeded",
        error_code="stories_blocked",
        error_detail=json.dumps(
            [{"rank": 12, "reason": "evidence_failed: http_403"}]
        ),
    )
    session.add(run)
    session.flush()
    story = EditorialStory(
        editorial_run_id=run.id,
        article_id=article.id,
        rank=1,
        category="technology_ai",
        headline="Fixture headline",
        body="body",
    )
    session.add(story)
    session.flush()
    edition = Edition(
        edition_date=date(2026, 11, 25), status="validated",
        epub_key="/data/editions/2026-11-25.epub", epub_sha256=SHA,
    )
    session.add(edition)
    session.flush()
    session.add(EditionStory(edition_id=edition.id, story_id=story.id, position=1))
    session.add(
        Delivery(
            edition_id=edition.id,
            destination_key="kindle",
            epub_sha256=SHA,
            status="smtp_accepted",
        )
    )
    session.commit()
    return source


def test_dashboard_data_sections(sessions):
    with sessions() as session:
        source = seed_dashboard(session)
        data = dashboard_data(session)

    assert len(data["editions"]) == 1
    assert data["story_counts"][data["editions"][0].id] == 1
    delivery = data["deliveries"][data["editions"][0].id][0]
    assert delivery.status == "smtp_accepted"
    assert data["drafting"]["drafted"] == 1
    assert data["drafting"]["reasons"][0]["reason"] == "evidence_failed: http_403"
    feed = next(f for f in data["feeds"] if f["source"].id == source.id)
    assert feed["latest"].status == "succeeded"
    assert feed["streak"] == 0
    assert data["stats"]["articles_total"] == 1


def test_render_escapes_and_shows(sessions):
    with sessions() as session:
        seed_dashboard(session)
        html = render_html(dashboard_data(session))

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "smtp_accepted" in html
    assert "evidence_failed: http_403" in html
    assert "b" * 12 in html  # truncated sha prefix


def test_http_endpoints(sessions):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(sessions))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        body = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/", timeout=5
        ).read()
        assert b"The Kastle Daily" in body
        assert urllib.request.urlopen(
            f"http://127.0.0.1:{port}/healthz", timeout=5
        ).read() == b'{"status":"ok"}'
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
        assert missing.value.code == 404
    finally:
        server.shutdown()
