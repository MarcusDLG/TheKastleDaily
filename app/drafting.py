"""Draft reviewable stories from the selected plan and article evidence.

One editorial run is recorded per edition date. Each produced story links
its source observations through editorial evidence rows, and the fetched
article text is kept as an evidence acquisition for claim checking and
regeneration. Fetch, extraction and generation are injected so tests and
CI never contact external providers.

Evidence text is untrusted data: generators must never treat it as
instructions, and output is schema-validated before a story is recorded.
Malformed or unsupported output blocks that story's slot.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Callable, Protocol

from sqlalchemy import func, select

from app.evidence import acquire, extract_text, fetch_document, fetch_image
from app.models import (
    Article,
    ArticleSource,
    EditorialEvidence,
    EditorialRun,
    EditorialStory,
    EvidenceAcquisition,
)

MIN_PARAGRAPHS = 2
MAX_PARAGRAPHS = 4
PARAGRAPH_MIN = 80
PARAGRAPH_MAX = 2000
HEADLINE_MAX = 200
LABEL_MAX = 100


@dataclass(frozen=True)
class DraftOutput:
    headline: str
    paragraphs: tuple[str, ...]
    sources: tuple[dict, ...]


class Generator(Protocol):
    """Turns one selected story plus extracted evidence into a draft.

    `generate` may return None to decline a story. Implementations report
    usage on the run record via the token and cost attributes. `check`,
    when given, returns a rejection reason (or None when the output is
    acceptable) so providers can repair before the story is blocked.
    """

    name: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal

    def generate(
        self,
        story: dict,
        evidence_text: str,
        check: Callable[[DraftOutput], str | None] | None = None,
    ) -> DraftOutput | None:
        ...


class TemplateGenerator:
    """Deterministic local drafter producing attributed excerpts.

    Keeps the pipeline useful before a model provider is enabled: the
    headline comes from the feed and the body quotes the first substantive
    evidence paragraphs with source attribution.
    """

    name = "template"
    input_tokens = output_tokens = 0
    estimated_cost_usd = Decimal("0")

    def generate(
        self,
        story: dict,
        evidence_text: str,
        check: Callable[[DraftOutput], str | None] | None = None,
    ) -> DraftOutput | None:
        blocks = [b.strip() for b in evidence_text.split("\n\n") if b.strip()]
        if len(blocks) < MIN_PARAGRAPHS:
            blocks = [b.strip() for b in evidence_text.split("\n") if b.strip()]
        paragraphs = tuple(
            b[:PARAGRAPH_MAX] for b in blocks if len(b) >= PARAGRAPH_MIN
        )
        output = DraftOutput(
            headline=story["title"].strip()[:HEADLINE_MAX],
            paragraphs=paragraphs[:MAX_PARAGRAPHS],
            sources=({"url": story["url"], "label": story["publisher"]},),
        )
        if check is not None and (reason := check(output)) is not None:
            raise ValueError(reason)
        return output


def validate_draft(output: DraftOutput, allowed_urls: set) -> DraftOutput:
    """Enforce the draft contract; invalid output is rejected by raising."""
    headline = output.headline.strip()
    if not headline or len(headline) > HEADLINE_MAX:
        raise ValueError("Draft headline is missing or oversized")
    paragraphs = tuple(p.strip() for p in output.paragraphs if p.strip())
    if len(paragraphs) < MIN_PARAGRAPHS:
        raise ValueError("Draft needs at least two substantive paragraphs")
    if any(len(p) < PARAGRAPH_MIN or len(p) > PARAGRAPH_MAX for p in paragraphs):
        raise ValueError("Draft paragraph length is out of bounds")
    if not output.sources:
        raise ValueError("Draft claims must reference evidence sources")
    for source in output.sources:
        label = (source.get("label") or "").strip()
        if source.get("url") not in allowed_urls or not label or len(label) > LABEL_MAX:
            raise ValueError("Draft source does not trace to evidence records")
    return DraftOutput(headline, paragraphs, output.sources)


def run_drafting(
    session,
    plan,
    *,
    fetch=fetch_document,
    extract=extract_text,
    generator=None,
    fetch_image=fetch_image,
):
    """Draft one edition's stories; a second pass for the date is suppressed."""
    generator = generator or TemplateGenerator()
    edition_date = date.fromisoformat(plan["edition_date"])

    existing = session.scalar(
        select(EditorialRun).where(
            EditorialRun.edition_date == edition_date,
            EditorialRun.status == "succeeded",
        )
    )
    if existing is not None:
        return {
            "edition_date": plan["edition_date"],
            "status": "already_drafted",
            "run_id": str(existing.id),
            "drafted": session.scalar(
                select(func.count(EditorialStory.id)).where(
                    EditorialStory.editorial_run_id == existing.id
                )
            ),
            "blocked": 0,
        }

    run = EditorialRun(
        edition_date=edition_date,
        model=generator.name,
        plan=json.dumps(plan, sort_keys=True, default=str),
    )
    session.add(run)
    session.flush()

    drafted = 0
    blocked = 0
    blocked_reasons = []
    for rank, story in enumerate(plan["stories"], start=1):
        article = session.get(Article, story["article_id"])
        if article is None:
            blocked += 1
            blocked_reasons.append(
                {"rank": rank, "reason": "article_missing"}
            )
            continue
        acquisition = acquire(
            session, article, fetch=fetch, extract=extract, fetch_image=fetch_image
        )
        if not acquisition.extracted_text:
            blocked += 1
            blocked_reasons.append(
                {
                    "rank": rank,
                    "reason": f"evidence_{acquisition.status}: {acquisition.detail}",
                }
            )
            continue
        allowed = set(
            session.scalars(
                select(ArticleSource.source_url).where(
                    ArticleSource.article_id == article.id
                )
            )
        ) | {article.canonical_url}
        def check(output):
            try:
                validate_draft(output, allowed)
            except (ValueError, AttributeError, TypeError) as error:
                return str(error)
            return None

        try:
            generated = generator.generate(
                dict(story, observed_urls=sorted(allowed)),
                acquisition.extracted_text,
                check=check,
            )
            if generated is None:
                raise ValueError("generator declined the story")
            output = validate_draft(generated, allowed)
        except (ValueError, AttributeError, TypeError) as error:
            blocked += 1
            blocked_reasons.append({"rank": rank, "reason": str(error)})
            continue
        record = EditorialStory(
            editorial_run_id=run.id,
            article_id=article.id,
            rank=rank,
            category=story["category"],
            headline=output.headline,
            body="\n\n".join(output.paragraphs),
        )
        session.add(record)
        session.flush()
        for source_id in session.scalars(
            select(ArticleSource.id).where(ArticleSource.article_id == article.id)
        ):
            session.add(
                EditorialEvidence(
                    story_id=record.id,
                    article_source_id=source_id,
                    evidence_note=(
                        f"Evidence acquired {acquisition.fetched_at.isoformat()} "
                        f"from {acquisition.url}; "
                        f"{len(acquisition.extracted_text)} characters extracted."
                    ),
                )
            )
        drafted += 1

    run.status = "succeeded"
    if blocked:
        run.error_code = "stories_blocked"
        run.error_detail = json.dumps(blocked_reasons[:10])
    run.finished_at = datetime.now(UTC)
    run.input_tokens = generator.input_tokens
    run.output_tokens = generator.output_tokens
    run.estimated_cost_usd = generator.estimated_cost_usd
    session.flush()
    return {
        "edition_date": plan["edition_date"],
        "status": "drafted",
        "run_id": str(run.id),
        "drafted": drafted,
        "blocked": blocked,
    }


def to_render_drafts(session, run_id):
    """Produce the edition renderer's drafts contract for one run's stories."""
    stories = session.scalars(
        select(EditorialStory)
        .where(EditorialStory.editorial_run_id == run_id)
        .order_by(EditorialStory.rank)
    ).all()
    drafts = []
    for story in stories:
        rows = session.execute(
            select(ArticleSource.source_url, ArticleSource.attributed_to)
            .join(
                EditorialEvidence,
                EditorialEvidence.article_source_id == ArticleSource.id,
            )
            .where(EditorialEvidence.story_id == story.id)
        ).all()
        draft = {
            "article_id": str(story.article_id),
            "headline": story.headline,
            "paragraphs": story.body.split("\n\n"),
            "sources": [
                {"url": url, "label": publisher} for url, publisher in rows
            ],
        }
        acquisition = session.scalar(
            select(EvidenceAcquisition).where(
                EvidenceAcquisition.article_id == story.article_id
            )
        )
        if acquisition is not None and acquisition.photo_file:
            draft["photo"] = {
                "file": acquisition.photo_file,
                "alt": acquisition.photo_alt or story.headline.strip(),
                "credit": f"Image: {rows[0][1]}" if rows else "Image: publisher",
            }
        drafts.append(draft)
    return {"stories": drafts}
