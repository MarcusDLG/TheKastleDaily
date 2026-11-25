from datetime import UTC, datetime, time as dtime
from zoneinfo import ZoneInfo

from app import schedule

ZONE = ZoneInfo("America/New_York")
AT = dtime(7, 0)


def utc(local_iso):
    return datetime.fromisoformat(local_iso).replace(tzinfo=ZONE).astimezone(UTC)


def test_not_due_before_edition_time():
    assert schedule.edition_due(utc("2026-11-25T06:59"), None, ZONE, AT) is None


def test_due_after_edition_time_when_never_run():
    assert schedule.edition_due(utc("2026-11-25T07:00"), None, ZONE, AT) == "2026-11-25"


def test_suppressed_after_success():
    assert (
        schedule.edition_due(utc("2026-11-25T09:00"), "2026-11-25", ZONE, AT) is None
    )


def test_catch_up_when_worker_starts_late():
    assert schedule.edition_due(utc("2026-11-25T18:30"), "2026-11-24", ZONE, AT) == (
        "2026-11-25"
    )


def test_spring_forward_still_fires_at_seven_local():
    # 2026-03-08: 02:00 jumps to 03:00 in America/New_York.
    assert (
        schedule.edition_due(utc("2026-03-08T07:00"), "2026-03-07", ZONE, AT)
        == "2026-03-08"
    )
    assert schedule.edition_due(utc("2026-03-08T06:30"), "2026-03-07", ZONE, AT) is None


def test_fall_back_does_not_double_fire():
    # 2026-11-01: 02:00 repeats in America/New_York.
    assert (
        schedule.edition_due(utc("2026-11-01T07:00"), "2026-10-31", ZONE, AT)
        == "2026-11-01"
    )
    assert (
        schedule.edition_due(utc("2026-11-01T08:00"), "2026-11-01", ZONE, AT) is None
    )


def test_state_round_trip_and_corruption_tolerance(tmp_path):
    path = tmp_path / "run-state.json"
    schedule.write_state(path, last_edition="2026-11-25", last_outcome="succeeded")
    state = schedule.read_state(path)
    assert state["last_edition"] == "2026-11-25"
    assert "wake" in state

    path.write_text("{ not json")
    assert schedule.read_state(path) == {}


def test_failed_attempts_are_counted_per_edition(tmp_path):
    path = tmp_path / "run-state.json"
    schedule.write_state(path, failed_date="2026-11-25", failed_attempts=1)
    schedule.write_state(path, failed_date="2026-11-25", failed_attempts=2)
    assert schedule.read_state(path)["failed_attempts"] == 2

    # A new edition day resets the retry budget.
    schedule.write_state(path, last_edition="2026-11-25", failed_attempts=0)
    assert schedule.read_state(path)["failed_attempts"] == 0
