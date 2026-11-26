import base64
import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin import (
    add_source,
    dashboard_data,
    make_handler,
    render_html,
    set_source_state,
)
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

CATEGORIES = ["technology_ai", "motorsport"]
TOKEN = "test-token"

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
        html = render_html(
            dashboard_data(session), token=TOKEN, writable=False,
            categories=CATEGORIES, editorial={},
        )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "smtp_accepted" in html
    assert "evidence_failed: http_403" in html
    assert "b" * 12 in html  # truncated sha prefix
    assert "Add feed" not in html  # read-only mode hides write controls


def test_render_writable_shows_controls(sessions):
    with sessions() as session:
        seed_dashboard(session)
        html = render_html(
            dashboard_data(session), token=TOKEN, writable=True,
            categories=CATEGORIES,
            editorial={
                "target_articles": 15,
                "edition_time": "07:00",
                "timezone": "America/New_York",
                "weights": {"technology_ai": 60, "motorsport": 40},
            },
        )
    assert "Add feed" in html
    assert TOKEN in html  # form token embedded
    assert "value='disabled'" in html  # state buttons rendered
    assert "w_technology_ai" in html  # weight inputs rendered
    assert "Genre weights" in html


def _serve(sessions, password=None):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(
            sessions, token=TOKEN, username="admin", password=password,
            categories=CATEGORIES,
        ),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _post(port, path, fields, auth=None):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=urlencode(fields).encode(),
        method="POST",
    )
    if auth:
        request.add_header(
            "Authorization",
            "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode(),
        )
    opener = urllib.request.build_opener(NoRedirect)
    return opener.open(request, timeout=5)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def test_http_endpoints(sessions):
    server, port = _serve(sessions)
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


def test_writes_forbidden_without_password(sessions):
    server, port = _serve(sessions)
    try:
        with pytest.raises(urllib.error.HTTPError) as denied:
            _post(port, "/sources/add", {"endpoint": "x"}, None)
        assert denied.value.code == 403
    finally:
        server.shutdown()


def test_auth_gate_and_csrf(sessions):
    server, port = _serve(sessions, password="hunter2")
    try:
        with pytest.raises(urllib.error.HTTPError) as unauth:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
        assert unauth.value.code == 401
        # healthz stays unauthenticated for the compose healthcheck
        assert urllib.request.urlopen(
            f"http://127.0.0.1:{port}/healthz", timeout=5
        ).status == 200
        # authed POST with a bad token still fails closed
        with pytest.raises(urllib.error.HTTPError) as bad_token:
            _post(
                port, "/sources/state",
                {"id": "x", "approval": "approved", "token": "wrong"},
                auth=("admin", "hunter2"),
            )
        assert bad_token.value.code == 403
    finally:
        server.shutdown()


def test_add_and_transition_feed(sessions):
    server, port = _serve(sessions, password="hunter2")
    auth = ("admin", "hunter2")
    try:
        with pytest.raises(urllib.error.HTTPError) as added_redirect:
            _post(
                port, "/sources/add",
                {
                    "token": TOKEN,
                    "endpoint": "https://new.example.com/rss",
                    "publisher": "New Feed",
                    "category": "technology_ai",
                    "kind": "rss",
                },
                auth,
            )
        assert added_redirect.value.code == 303
        assert added_redirect.value.headers["Location"].startswith("/?ok=")
        with sessions() as session:
            added = session.query(Source).filter_by(
                endpoint="https://new.example.com/rss"
            ).one()
            assert added.approval == "approved"
        with pytest.raises(urllib.error.HTTPError) as rejected:
            _post(
                port, "/sources/add",
                {
                    "token": TOKEN,
                    "endpoint": "https://new.example.com/rss",
                    "publisher": "New Feed",
                    "category": "technology_ai",
                },
                auth,
            )
        assert rejected.value.code == 303
        assert "err=" in rejected.value.headers["Location"]
        with pytest.raises(urllib.error.HTTPError) as disabled:
            _post(
                port, "/sources/state",
                {"token": TOKEN, "id": str(added.id), "approval": "disabled"},
                auth,
            )
        assert disabled.value.code == 303
        with sessions() as session:
            assert session.get(Source, added.id).approval == "disabled"
    finally:
        server.shutdown()


def test_add_source_validation(sessions):
    with sessions() as session:
        with pytest.raises(ValueError, match="http"):
            add_source(session, {"endpoint": "not-a-url"}, CATEGORIES)
        with pytest.raises(ValueError, match="publisher"):
            add_source(
                session, {"endpoint": "https://x.example.com"}, CATEGORIES
            )
        with pytest.raises(ValueError, match="category"):
            add_source(
                session,
                {"endpoint": "https://x.example.com", "publisher": "X",
                 "category": "nonsense"},
                CATEGORIES,
            )


def test_set_source_state_validation(sessions):
    with sessions() as session:
        source = seed_dashboard(session)
        session.commit()
        set_source_state(session, str(source.id), "disabled")
        session.commit()
        assert source.approval == "disabled"
        with pytest.raises(ValueError, match="approval"):
            set_source_state(session, str(source.id), "bogus")
        with pytest.raises(ValueError, match="unknown source"):
            set_source_state(session, str(uuid4()), "approved")


def test_editorial_save(sessions, tmp_path, monkeypatch):
    import yaml

    target = tmp_path / "editorial.yaml"
    target.write_text(
        yaml.safe_dump(
            {
                "target_articles": 15,
                "timezone": "America/New_York",
                "edition_time": "07:00",
                "weights": {"technology_ai": 60, "motorsport": 40},
                "social_video_sources": ["youtube"],
            }
        )
    )
    monkeypatch.setenv("KASTLE_EDITORIAL_CONFIG", str(target))
    server, port = _serve(sessions, password="hunter2")
    auth = ("admin", "hunter2")
    try:
        with pytest.raises(urllib.error.HTTPError) as saved:
            _post(
                port, "/editorial/save",
                {
                    "token": TOKEN,
                    "target_articles": "12",
                    "edition_time": "06:30",
                    "timezone": "America/New_York",
                    "w_technology_ai": "70",
                    "w_motorsport": "30",
                    "new_category": "",
                },
                auth,
            )
        assert saved.value.code == 303
        saved_config = yaml.safe_load(target.read_text())
        assert saved_config["edition_time"] == "06:30"
        assert saved_config["target_articles"] == 12
        assert saved_config["weights"] == {
            "technology_ai": 70, "motorsport": 30
        }
        assert saved_config["social_video_sources"] == ["youtube"]
        # Invalid: weights don't sum to 100 → err flash, file unchanged
        with pytest.raises(urllib.error.HTTPError) as bad:
            _post(
                port, "/editorial/save",
                {
                    "token": TOKEN,
                    "target_articles": "12",
                    "edition_time": "06:30",
                    "timezone": "America/New_York",
                    "w_technology_ai": "70",
                    "w_motorsport": "31",
                },
                auth,
            )
        assert bad.value.code == 303
        assert "err=" in bad.value.headers["Location"]
        assert yaml.safe_load(target.read_text())["weights"]["motorsport"] == 30
    finally:
        server.shutdown()
