"""Exercise the migrated schema using only the application's database login."""

from datetime import date
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.database import database_engine, session_factory
from app.models import (
    Article,
    ArticleSource,
    Delivery,
    DeliveryAttempt,
    Edition,
    EditionStory,
    EditorialEvidence,
    EditorialRun,
    EditorialStory,
    IngestionRun,
    Source,
)


def expect_database_error(session, sql, sqlstate, parameters=None):
    try:
        with session.begin_nested():
            session.execute(text(sql), parameters)
    except DBAPIError as exc:
        assert exc.orig.sqlstate == sqlstate, (exc.orig.sqlstate, sqlstate)
    else:
        raise AssertionError(f"Expected {sqlstate} for {sql}")


def add(session, record):
    session.add(record)
    session.flush()
    return record.id


engine = database_engine()
today = date(2026, 11, 1)
checksum = "a" * 64
with session_factory(engine)() as session:
    assert session.scalar(text("SHOW server_version_num")).startswith("17")
    assert session.scalar(text("SHOW timezone")) == "UTC"
    assert session.scalar(text("SHOW data_checksums")) == "on"
    assert session.scalar(text("SELECT current_user")) == "kastle_app"
    for database in ("postgres", "template1"):
        assert not session.scalar(
            text("SELECT has_database_privilege(:database, 'CONNECT')"),
            {"database": database},
        )

    denied = [
        "CREATE TABLE newspaper.forbidden (id int)",
        "CREATE TEMP TABLE forbidden (id int)",
        "SELECT * FROM newspaper.alembic_version",
        "ALTER TABLE newspaper.editions ADD COLUMN forbidden int",
        "DELETE FROM newspaper.editions",
        "UPDATE newspaper.sources SET approval = 'approved'",
        "SET ROLE kastle_migrator",
        "SET ROLE kastle_bootstrap",
    ]
    for statement in denied:
        expect_database_error(session, statement, "42501")

    source_id = session.scalar(select(Source.id).where(Source.approval == "approved"))
    assert source_id is not None
    source = session.get(Source, source_id)
    source.etag = '"acceptance"'
    ingestion_id = add(session, IngestionRun(source_id=source_id))
    article_id = add(session, Article(canonical_url="https://example.invalid/story", title="Story"))
    provenance = dict(
        article_id=article_id,
        source_id=source_id,
        ingestion_run_id=ingestion_id,
        external_id="test",
        source_url="https://example.invalid/original",
        attributed_to="Acceptance fixture",
    )
    provenance_id = add(session, ArticleSource(**provenance))
    for changes, state in [
        ({}, "23505"),
        ({"external_id": "different", "ingestion_run_id": uuid4()}, "23503"),
    ]:
        expect_database_error(
            session,
            "INSERT INTO newspaper.article_sources "
            "(article_id, source_id, ingestion_run_id, external_id, source_url, attributed_to) "
            "VALUES (:article_id, :source_id, :ingestion_run_id, :external_id, "
            ":source_url, :attributed_to)",
            state,
            provenance | changes,
        )

    run_id = add(session, EditorialRun(edition_date=today, model="mock"))
    story_id = add(session, EditorialStory(
        editorial_run_id=run_id, article_id=article_id, rank=1,
        category="formula_1", headline="Story", body="Fixture"
    ))
    session.add(EditorialEvidence(
        story_id=story_id, article_source_id=provenance_id, evidence_note="Fixture"
    ))
    edition_id = add(session, Edition(
        edition_date=today, status="validated", epub_key="edition.epub", epub_sha256=checksum
    ))
    session.add(EditionStory(edition_id=edition_id, story_id=story_id, position=1))
    delivery_id = add(session, Delivery(
        edition_id=edition_id, destination_key="test", epub_sha256=checksum
    ))
    add(session, DeliveryAttempt(delivery_id=delivery_id, attempt_number=1, outcome="ambiguous"))

    expect_database_error(
        session, "INSERT INTO newspaper.editions (edition_date) VALUES (:day)",
        "23505", {"day": today}
    )
    expect_database_error(
        session, "INSERT INTO newspaper.deliveries (edition_id, destination_key, epub_sha256) "
        "VALUES (:edition, 'test', :checksum)", "23505",
        {"edition": edition_id, "checksum": checksum}
    )
    expect_database_error(
        session, "INSERT INTO newspaper.delivery_attempts (delivery_id, attempt_number) "
        "VALUES (:delivery, 1)", "23505", {"delivery": delivery_id}
    )
    expect_database_error(
        session, "INSERT INTO newspaper.editions (edition_date, status) "
        "VALUES (DATE '2026-11-02', 'validated')", "23514"
    )
    session.commit()

with session_factory(engine)() as session:
    row = session.scalar(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id == delivery_id))
    assert row.outcome == "ambiguous"

engine.dispose()
print("PostgreSQL 17 persistence and privilege checks passed")
