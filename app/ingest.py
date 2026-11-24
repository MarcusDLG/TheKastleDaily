"""Run one RSS ingestion pass as the application database role."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import database_engine, session_factory
from app.models import Article, ArticleSource, IngestionRun, Source
from app.rss import FeedError, fetch_feed, parse_feed


def _approved_rss():
    return select(Source).where(Source.kind == "rss", Source.approval == "approved")


def _store_items(session, source, run, items):
    if not items:
        return
    known_ids = set(
        session.scalars(
            select(ArticleSource.external_id).where(
                ArticleSource.source_id == source.id,
                ArticleSource.external_id.in_([item.external_id for item in items]),
            )
        )
    )
    # Stable order prevents cross-source upserts from acquiring locks in opposite order.
    unique_items = {}
    for item in items:
        if item.external_id not in known_ids:
            unique_items.setdefault(item.external_id, item)
    for item in sorted(unique_items.values(), key=lambda item: item.url):
        article_id = session.scalar(
            insert(Article)
            .values(canonical_url=item.url, title=item.title)
            .on_conflict_do_nothing(index_elements=[Article.canonical_url])
            .returning(Article.id)
        )
        if article_id is None:
            article_id = session.scalar(
                select(Article.id).where(Article.canonical_url == item.url)
            )
        session.add(
            ArticleSource(
                article_id=article_id,
                source_id=source.id,
                ingestion_run_id=run.id,
                external_id=item.external_id,
                source_url=item.url,
                attributed_to=source.publisher,
                published_at=item.published_at,
            )
        )


def ingest_sources(sessions, fetch=fetch_feed):
    with sessions() as session:
        source_ids = list(session.scalars(_approved_rss().with_only_columns(Source.id)))

    results = {}
    for source_id in source_ids:
        with sessions.begin() as session:
            source = session.scalar(
                _approved_rss()
                .where(Source.id == source_id)
                .with_for_update(skip_locked=True)
            )
            if source is None:
                continue
            run = IngestionRun(source_id=source_id)
            session.add(run)
            session.flush()
            try:
                response = fetch(source.endpoint, source.etag, source.last_modified)
                if response.body is not None:
                    _store_items(session, source, run, parse_feed(response.body))
                source.etag = response.etag
                source.last_modified = response.last_modified
                run.status = "succeeded"
                results[source_id] = (
                    "not_modified" if response.body is None else "succeeded"
                )
            except FeedError as error:
                run.status = "failed"
                run.error_code = str(error)
                results[source_id] = "failed"
            run.finished_at = datetime.now(UTC)
    return results


def main():
    engine = database_engine()
    try:
        results = ingest_sources(session_factory(engine))
    finally:
        engine.dispose()
    for source_id, status in results.items():
        print(f"{source_id} {status}")
    print(f"Processed {len(results)} approved RSS sources.")
    return int("failed" in results.values())


if __name__ == "__main__":
    raise SystemExit(main())
