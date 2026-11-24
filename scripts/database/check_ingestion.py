"""Run the real ingestion service against PostgreSQL with mocked publisher responses."""

from collections import Counter

from sqlalchemy import func, select

from app.database import database_engine, session_factory
from app.ingest import ingest_sources
from app.models import Article, ArticleSource, IngestionRun, Source
from app.rss import FeedResponse

FEED = b"""<rss><channel>
<item><guid>one</guid><title>Fixture</title><link>https://example.invalid/ingestion</link></item>
<item><guid>one</guid><title>Changed URL</title><link>https://example.invalid/ignored</link></item>
</channel></rss>"""


def fetch(endpoint, etag, last_modified):
    assert last_modified is None
    if endpoint.endswith("/bad-feed"):
        return FeedResponse(b"<html/>", None, None)
    assert endpoint.endswith(("/feed", "/second-feed"))
    assert etag in ('"acceptance"', '"pilot"', None)
    return FeedResponse(FEED, '"pilot"', None)


def unchanged(endpoint, etag, last_modified):
    if endpoint.endswith("/bad-feed"):
        return FeedResponse(b"<invalid", None, None)
    assert etag == '"pilot"'
    return FeedResponse(None, etag, last_modified)


engine = database_engine()
sessions = session_factory(engine)
expected = {"failed": 1, "succeeded": 2}
assert Counter(ingest_sources(sessions, fetch).values()) == expected
assert Counter(ingest_sources(sessions, fetch).values()) == expected
assert Counter(ingest_sources(sessions, unchanged).values()) == {
    "failed": 1,
    "not_modified": 2,
}

with sessions() as session:
    article = session.scalar(
        select(Article).where(
            Article.canonical_url == "https://example.invalid/ingestion"
        )
    )
    assert article is not None
    assert (
        session.scalar(
            select(func.count())
            .select_from(ArticleSource)
            .where(ArticleSource.article_id == article.id)
        )
        == 2
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.canonical_url == "https://example.invalid/ignored")
        )
        == 0
    )
    failures = session.scalars(
        select(IngestionRun.error_code)
        .join(Source)
        .where(Source.endpoint == "https://example.invalid/bad-feed")
    ).all()
    assert Counter(failures) == {"unsupported_feed": 2, "invalid_xml": 1}

engine.dispose()
print("RSS persistence, deduplication and conditional responses passed")
