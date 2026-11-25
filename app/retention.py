"""Bounded retention: prune rows and edition artifacts past the window.

The paper's footprint accretes daily — articles, evidence payloads,
photos and EPUBs would grow forever. Retention keeps the last
RETENTION_DAYS days and removes everything older, children before
parents so foreign keys stay satisfied. The feed registry (`sources`)
is configuration and is never pruned; file deletions are best-effort
so a locked or missing file never fails the pass.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, or_, select

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
    EvidenceAcquisition,
    IngestionRun,
)

RETENTION_DAYS = 30


def _ids(session, model, *clauses):
    return list(session.scalars(select(model.id).where(*clauses)))


def prune(session, directory, days: int = RETENTION_DAYS, now=None):
    """Delete artifacts and rows older than `days`. Returns a count summary."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    directory = Path(directory)

    files_removed = 0
    for path in (
        *directory.glob("*.epub"),
        *directory.glob("cover-*.png"),
        *directory.glob("photos/*"),
    ):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                path.unlink()
                files_removed += 1
        except OSError:
            pass  # A file that can't be inspected or removed is left alone.

    old_articles = _ids(session, Article, Article.created_at < cutoff)
    old_runs = _ids(session, EditorialRun, EditorialRun.created_at < cutoff)
    old_ingests = _ids(session, IngestionRun, IngestionRun.created_at < cutoff)
    old_editions = _ids(session, Edition, Edition.created_at < cutoff)

    # Junction rows carry no timestamp, so they follow their parents;
    # children of expired rows are expired too.
    old_stories = _ids(
        session,
        EditorialStory,
        or_(
            EditorialStory.created_at < cutoff,
            EditorialStory.article_id.in_(old_articles),
            EditorialStory.editorial_run_id.in_(old_runs),
        ),
    )
    old_sources = _ids(
        session,
        ArticleSource,
        or_(
            ArticleSource.created_at < cutoff,
            ArticleSource.article_id.in_(old_articles),
            ArticleSource.ingestion_run_id.in_(old_ingests),
        ),
    )
    old_deliveries = _ids(
        session,
        Delivery,
        or_(Delivery.created_at < cutoff, Delivery.edition_id.in_(old_editions)),
    )

    counts = {}
    counts["editorial_evidence"] = session.execute(
        delete(EditorialEvidence).where(
            or_(
                EditorialEvidence.story_id.in_(old_stories),
                EditorialEvidence.article_source_id.in_(old_sources),
            )
        )
    ).rowcount
    counts["edition_stories"] = session.execute(
        delete(EditionStory).where(
            or_(
                EditionStory.edition_id.in_(old_editions),
                EditionStory.story_id.in_(old_stories),
            )
        )
    ).rowcount
    counts["delivery_attempts"] = session.execute(
        delete(DeliveryAttempt).where(
            DeliveryAttempt.delivery_id.in_(old_deliveries)
        )
    ).rowcount
    counts["deliveries"] = session.execute(
        delete(Delivery).where(Delivery.id.in_(old_deliveries))
    ).rowcount
    counts["editorial_stories"] = session.execute(
        delete(EditorialStory).where(EditorialStory.id.in_(old_stories))
    ).rowcount
    counts["evidence_acquisitions"] = session.execute(
        delete(EvidenceAcquisition).where(
            or_(
                EvidenceAcquisition.created_at < cutoff,
                EvidenceAcquisition.article_id.in_(old_articles),
            )
        )
    ).rowcount
    counts["article_sources"] = session.execute(
        delete(ArticleSource).where(ArticleSource.id.in_(old_sources))
    ).rowcount
    counts["articles"] = session.execute(
        delete(Article).where(Article.id.in_(old_articles))
    ).rowcount
    counts["editorial_runs"] = session.execute(
        delete(EditorialRun).where(EditorialRun.id.in_(old_runs))
    ).rowcount
    counts["editions"] = session.execute(
        delete(Edition).where(Edition.id.in_(old_editions))
    ).rowcount
    counts["ingestion_runs"] = session.execute(
        delete(IngestionRun).where(IngestionRun.id.in_(old_ingests))
    ).rowcount
    counts["files_removed"] = files_removed
    counts["status"] = "pruned"
    return counts
