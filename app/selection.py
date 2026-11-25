"""Select the candidate stories for one local edition without publishing it."""

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import func, select

from app.database import database_engine, session_factory
from app.models import (
    Article,
    ArticleSource,
    Edition,
    EditionStory,
    EditorialStory,
    Source,
)

RESERVED = frozenset({"sim_racing", "maker_radio"})
FRESH_WINDOW = timedelta(days=2)
RESERVE_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class Candidate:
    article_id: UUID
    provenance_id: UUID
    title: str
    url: str
    publisher: str
    category: str
    timestamp: datetime


def allocate_slots(target, weights):
    total = sum(weights.values())
    if target < 1 or total <= 0 or any(weight < 0 for weight in weights.values()):
        raise ValueError(
            "Editorial target and weights must define a positive allocation"
        )
    quotas = {key: target * weight // total for key, weight in weights.items()}
    priority = sorted(weights, key=lambda key: (-(target * weights[key] % total), key))
    for key in priority[: target - sum(quotas.values())]:
        quotas[key] += 1
    return quotas


def select_stories(candidates, target, weights, cutoff):
    quotas = allocate_slots(target, weights)
    ordered = sorted(
        (
            item
            for item in candidates
            if cutoff - RESERVE_WINDOW <= item.timestamp <= cutoff
            and weights.get(item.category, 0) > 0
        ),
        key=lambda item: (-item.timestamp.timestamp(), item.url, item.provenance_id),
    )

    # Reserve a place before filling the other sections, including cross-posted articles.
    reserved = next((item for item in ordered if item.category in RESERVED), None)
    if reserved and not quotas[reserved.category]:
        donor = max(quotas, key=lambda key: (quotas[key], key))
        quotas[donor] -= 1
        quotas[reserved.category] += 1

    selected = [reserved] if reserved else []
    used = {reserved.article_id} if reserved else set()
    counts = Counter(item.category for item in selected)
    for item in ordered:
        if item.timestamp < cutoff - FRESH_WINDOW or item.article_id in used:
            continue
        if counts[item.category] >= quotas[item.category]:
            continue
        used.add(item.article_id)
        counts[item.category] += 1
        selected.append(item)

    category_order = {category: index for index, category in enumerate(weights)}
    selected.sort(
        key=lambda item: (
            category_order[item.category],
            -item.timestamp.timestamp(),
            item.url,
        )
    )
    return {
        "target": target,
        "coverage_floor_met": reserved is not None,
        "shortfall": target - len(selected),
        "coverage": {
            key: {"target": count, "selected": counts[key]}
            for key, count in quotas.items()
        },
        "stories": [
            asdict(item)
            | {
                "reserved": item == reserved,
                "archived": item.timestamp < cutoff - FRESH_WINDOW,
            }
            for item in selected
        ],
    }


def read_candidates(session, cutoff, edition_date):
    timestamp = func.coalesce(ArticleSource.published_at, ArticleSource.created_at)
    previously_used = (
        select(EditorialStory.article_id)
        .join(EditionStory, EditionStory.story_id == EditorialStory.id)
        .join(Edition, Edition.id == EditionStory.edition_id)
        .where(Edition.edition_date < edition_date, Edition.status == "validated")
    )
    query = (
        select(
            Article.id,
            ArticleSource.id,
            Article.title,
            ArticleSource.source_url,
            ArticleSource.attributed_to,
            Source.category,
            timestamp,
        )
        .select_from(ArticleSource)
        .join(Article, Article.id == ArticleSource.article_id)
        .join(Source, Source.id == ArticleSource.source_id)
        .where(
            Source.approval == "approved",
            Source.kind == "rss",
            timestamp.between(cutoff - RESERVE_WINDOW, cutoff),
            ArticleSource.created_at <= cutoff,
            Article.id.not_in(previously_used),
        )
    )
    return [Candidate(*row) for row in session.execute(query)]


def build_plan(edition_date=None):
    """Compute the selection plan for one edition date (defaults to today)."""
    config = yaml.safe_load(Path("config/editorial.yaml").read_text())
    zone = ZoneInfo(config["timezone"])
    now = datetime.now(UTC)
    if edition_date is None:
        edition_date = now.astimezone(zone).date()
    if edition_date > now.astimezone(zone).date():
        raise ValueError("The edition date cannot be in the future")
    end = datetime.combine(edition_date + timedelta(days=1), time.min, zone)
    cutoff = min(now, end.astimezone(UTC) - timedelta(microseconds=1))

    engine = database_engine()
    try:
        with session_factory(engine)() as session:
            candidates = read_candidates(session, cutoff, edition_date)
        plan = select_stories(
            candidates, config["target_articles"], config["weights"], cutoff
        )
    finally:
        engine.dispose()
    return {"edition_date": edition_date.isoformat()} | plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", type=date.fromisoformat, help="New York edition date (YYYY-MM-DD)"
    )
    args = parser.parse_args()
    try:
        plan = build_plan(args.date)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(plan, default=str, indent=2))
    return 0 if plan["coverage_floor_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
