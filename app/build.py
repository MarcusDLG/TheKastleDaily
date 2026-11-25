"""Render and persist the validated EPUB for the day's editorial run.

The build is a pure function of the latest succeeded editorial run: the
selection plan stored on the run plus the run's persisted drafts. Stories
blocked during drafting drop out of the render plan and the coverage
floor is rechecked against what actually drafted; if the original reserve
pick was blocked, the newest surviving reserve-category story carries the
flag so the renderer's floor still reflects edition content.

The EPUB is rendered to a scratch file, hashed and moved into place
atomically, so a failed build never disturbs a previous artifact. The
editions row records the artifact path and SHA-256; edition story rows
map the renderer's order back to the run's stories so later selections
exclude articles already published in a validated edition.
"""

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select

from app.database import database_path
from app.drafting import to_render_drafts
from app.edition import render_epub
from app.models import Edition, EditionStory, EditorialRun, EditorialStory
from app.selection import RESERVED


def editions_dir() -> Path:
    """EPUBs live in an `editions` directory beside the database file."""
    db = database_path()
    base = Path(db).parent if db != ":memory:" else Path(".")
    return base / "editions"


def latest_succeeded_run(session, edition_date):
    """Return the newest succeeded editorial run for one edition date."""
    return session.scalar(
        select(EditorialRun)
        .where(
            EditorialRun.edition_date == edition_date,
            EditorialRun.status == "succeeded",
        )
        .order_by(EditorialRun.finished_at.desc(), EditorialRun.created_at.desc())
        .limit(1)
    )


def _timestamp(story) -> float:
    value = story.get("timestamp")
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _render_plan(plan, drafts) -> dict:
    """Restrict the stored plan to drafted stories and recheck the floor."""
    drafted = {draft["article_id"] for draft in drafts["stories"]}
    stories = [dict(story) for story in plan["stories"] if story["article_id"] in drafted]
    if not stories:
        raise ValueError("No drafted stories to render")
    reserve = [story for story in stories if story["category"] in RESERVED]
    if not reserve:
        raise ValueError("Blocked drafting removed the edition's reserved story")
    if not any(story.get("reserved") for story in reserve):
        newest = min(
            reserve,
            key=lambda story: (-_timestamp(story), story["url"], story["provenance_id"]),
        )
        newest["reserved"] = True
    counts = Counter(story["category"] for story in stories)
    coverage = {
        key: value | {"selected": counts.get(key, 0)}
        for key, value in plan["coverage"].items()
    }
    return plan | {
        "coverage_floor_met": True,
        "coverage": coverage,
        "stories": stories,
    }


def build_edition(session, run, directory) -> dict:
    """Render the run's EPUB and record it on the editions row.

    Idempotent: a validated edition whose artifact is still in place is
    reported without rebuilding. A failed build records the editions row
    as `failed` so the result is durable and the next pass can retry.
    """
    directory = Path(directory)
    filename = f"{run.edition_date.isoformat()}.epub"
    target = directory / filename
    edition = session.scalar(
        select(Edition).where(Edition.edition_date == run.edition_date)
    )
    if edition is not None and edition.status == "validated" and target.exists():
        return {
            "status": "already_validated",
            "edition_id": str(edition.id),
            "epub_key": edition.epub_key,
            "epub_sha256": edition.epub_sha256,
        }
    if edition is None:
        edition = Edition(edition_date=run.edition_date)
        session.add(edition)
        session.flush()

    scratch = directory / f".{filename}.tmp"
    try:
        if run.plan is None:
            raise ValueError("Editorial run has no stored selection plan")
        drafts = to_render_drafts(session, run.id)
        plan = _render_plan(json.loads(run.plan), drafts)
        directory.mkdir(parents=True, exist_ok=True)
        render_epub(plan, drafts, directory, scratch)
        checksum = hashlib.sha256(scratch.read_bytes()).hexdigest()
        scratch.replace(target)
        stories = {
            str(story.article_id): story
            for story in session.scalars(
                select(EditorialStory).where(
                    EditorialStory.editorial_run_id == run.id
                )
            )
        }
        rows = [
            EditionStory(
                edition_id=edition.id,
                story_id=stories[item["article_id"]].id,
                position=position,
            )
            for position, item in enumerate(plan["stories"], start=1)
        ]
    except (OSError, ValueError, KeyError, TypeError) as error:
        scratch.unlink(missing_ok=True)
        edition.status = "failed"
        session.flush()
        return {
            "status": "failed",
            "edition_id": str(edition.id),
            "error": str(error),
        }

    session.execute(delete(EditionStory).where(EditionStory.edition_id == edition.id))
    session.add_all(rows)
    edition.status = "validated"
    edition.epub_key = str(target)
    edition.epub_sha256 = checksum
    session.flush()
    return {
        "status": "validated",
        "edition_id": str(edition.id),
        "epub_key": edition.epub_key,
        "epub_sha256": checksum,
        "stories": len(rows),
    }
