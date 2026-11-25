from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.selection import Candidate, allocate_slots, select_stories

CUTOFF = datetime(2026, 11, 25, 5, tzinfo=UTC)
WEIGHTS = {
    "motorsport": 18,
    "sim_racing": 10,
    "technology_ai": 16,
    "software_engineering": 10,
    "maker_fabrication": 12,
    "radio_comms": 6,
    "space": 8,
    "culinary": 6,
    "visual_craft": 4,
    "homelab": 6,
    "life_systems": 4,
}


def candidate(number, category, *, age=0, article=None):
    return Candidate(
        UUID(int=article or number),
        UUID(int=number),
        f"Headline {number}",
        f"https://example.invalid/{number}",
        "Fixture",
        category,
        CUTOFF - timedelta(days=age),
    )


def test_editorial_weights_round_to_fifteen():
    assert allocate_slots(15, WEIGHTS) == dict(
        zip(WEIGHTS, (3, 1, 2, 1, 2, 1, 1, 1, 1, 1, 1))
    )


def test_reserve_can_use_recent_archive_and_deduplicates_across_sections():
    plan = select_stories(
        [
            candidate(1, "motorsport"),
            candidate(2, "maker_fabrication", age=5, article=1),
            candidate(3, "motorsport", age=3),
            candidate(4, "technology_ai"),
            candidate(5, "other"),
        ],
        15,
        WEIGHTS,
        CUTOFF,
    )
    assert plan["coverage_floor_met"]
    assert plan["shortfall"] == 13
    assert [row["category"] for row in plan["stories"]] == [
        "technology_ai",
        "maker_fabrication",
    ]
    assert plan["stories"][1]["reserved"] and plan["stories"][1]["archived"]


def test_fresh_sim_story_takes_precedence_over_archived_maker():
    plan = select_stories(
        [candidate(2, "maker_fabrication", age=4), candidate(1, "sim_racing")],
        15,
        WEIGHTS,
        CUTOFF,
    )
    assert len(plan["stories"]) == 1
    assert plan["stories"][0]["category"] == "sim_racing"
    assert plan["stories"][0]["reserved"] and not plan["stories"][0]["archived"]


def test_tiny_edition_transfers_the_slot_to_preserve_coverage():
    plan = select_stories(
        [candidate(2, "maker_fabrication"), candidate(1, "technology_ai")], 1, WEIGHTS, CUTOFF
    )
    assert plan["coverage_floor_met"]
    assert plan["shortfall"] == 0
    assert plan["stories"][0]["category"] == "maker_fabrication"


def test_missing_reserve_reports_shortfall_and_ignores_future_or_stale_candidates():
    plan = select_stories(
        [
            candidate(1, "sim_racing", age=31),
            candidate(2, "maker_fabrication", age=-1),
            candidate(3, "motorsport"),
        ],
        15,
        WEIGHTS,
        CUTOFF,
    )
    assert not plan["coverage_floor_met"]
    assert plan["shortfall"] == 14
    assert [row["category"] for row in plan["stories"]] == ["motorsport"]
