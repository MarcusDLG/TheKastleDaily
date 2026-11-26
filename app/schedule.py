"""Run the daily newspaper pipeline on a schedule.

One worker produces at most one edition per America/New_York calendar day,
at the configured edition time (default 07:00 local). Wake-ups recompute
the local time on every pass, so both DST transitions need no special
casing. Run state lives in a small JSON file next to the database; the
pipeline stages themselves are idempotent (ingestion deduplicates, edition
dates are unique).

`python -m app.schedule` loops forever (the container entrypoint).
`python -m app.schedule --once` runs the pipeline immediately, regardless
of the clock, and exits.
"""

import argparse
import json
import time
from datetime import UTC, date, datetime, time as dtime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import yaml

POLL_CAP_SECONDS = 900
MAX_ATTEMPTS_PER_EDITION = 3


def edition_config(config_path=None):
    if config_path is not None:
        config = yaml.safe_load(Path(config_path).read_text())
    else:
        from app.config import load_editorial_config

        config = load_editorial_config()
    zone = ZoneInfo(config["timezone"])
    raw = config.get("edition_time", "07:00")
    hour, minute = (int(part) for part in str(raw).split(":")[:2])
    return zone, dtime(hour, minute)


def state_path() -> Path:
    from app.database import database_path

    db = database_path()
    base = Path(db).parent if db != ":memory:" else Path(".")
    return base / "run-state.json"


def read_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_state(path: Path, **fields) -> None:
    state = read_state(path) | fields | {"wake": datetime.now(UTC).isoformat()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(path)


def edition_due(now_utc: datetime, last_edition: str | None, zone, at) -> str | None:
    """Return today's edition date (ISO) when it is due, else None."""
    local = now_utc.astimezone(zone)
    if local < datetime.combine(local.date(), at, zone):
        return None
    today = local.date().isoformat()
    return today if last_edition != today else None


def run_pipeline() -> None:
    """Migrate, register, ingest, select, draft, build, and deliver the edition."""
    from alembic.config import main as alembic_main

    from app.build import build_edition, editions_dir, latest_succeeded_run
    from app.database import database_engine, session_factory
    from app.delivery import (
        destinations,
        drain_safely,
        ensure_delivery,
        sync_recipients,
    )
    from app.drafting import run_drafting
    from app.ingest import ingest_sources
    from app.models import Edition
    from app.openai import openai_generator
    from app.pilot import register_sources
    from app.retention import prune
    from app.selection import build_plan

    alembic_main(argv=["upgrade", "head"])
    engine = database_engine()
    try:
        with engine.begin() as connection:
            register_sources(connection)
        # Additive env → registry sync runs every pass, so a disabled
        # address the admin removed stays removed.
        with session_factory(engine)() as session:
            sync_recipients(session)
            session.commit()
        ingest_sources(session_factory(engine))
        plan = build_plan(engine=engine)
        if plan["coverage_floor_met"]:
            with session_factory(engine)() as session:
                drafting = run_drafting(session, plan, generator=openai_generator())
                session.commit()
        else:
            drafting = {"status": "skipped", "reason": "coverage_floor_unmet"}

        # Building runs off the persisted run, so it also resumes a pass
        # that drafted successfully but failed before the EPUB landed.
        edition = {"status": "skipped", "reason": "no_drafted_run"}
        with session_factory(engine)() as session:
            run = latest_succeeded_run(session, date.fromisoformat(plan["edition_date"]))
            if run is not None:
                edition = build_edition(session, run, editions_dir())
                session.commit()
        delivery = {"status": "skipped", "reason": "not_applicable"}
        if edition.get("edition_id") and edition.get("status") in {
            "validated",
            "already_validated",
        }:
            with session_factory(engine)() as session:
                dests = destinations(session)
                row = session.get(Edition, UUID(edition["edition_id"]))
                if row is not None and dests:
                    queued = 0
                    for dest in dests:
                        _, created = ensure_delivery(session, row, dest)
                        queued += int(created)
                    session.commit()
                    delivery = {
                        "status": "queued" if queued else "exists",
                        "destinations": len(dests),
                    }
        outbox = drain_safely(engine)
        with session_factory(engine)() as session:
            retention = prune(session, editions_dir())
            session.commit()
        print(
            json.dumps(
                {
                    "selection": plan,
                    "drafting": drafting,
                    "edition": edition,
                    "delivery": delivery,
                    "outbox": outbox,
                    "retention": retention,
                },
                default=str,
                indent=2,
            )
        )
        if edition["status"] == "failed":
            raise RuntimeError(f"Edition build failed: {edition['error']}")
    finally:
        engine.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="run the pipeline now, then exit"
    )
    args = parser.parse_args(argv)
    zone, at = edition_config()
    path = state_path()

    from app.delivery import drain_safely

    if args.once:
        run_pipeline()
        today = datetime.now(UTC).astimezone(zone).date().isoformat()
        write_state(path, last_edition=today, last_outcome="manual")
        return 0

    while True:
        state = read_state(path)
        due = edition_due(datetime.now(UTC), state.get("last_edition"), zone, at)
        if due:
            attempts = (
                state.get("failed_attempts", 0) if state.get("failed_date") == due else 0
            )
            if attempts >= MAX_ATTEMPTS_PER_EDITION:
                write_state(path, last_outcome=f"exhausted:{due}")
            else:
                try:
                    run_pipeline()
                except Exception as error:  # a failed edition must not kill the worker
                    write_state(
                        path,
                        failed_date=due,
                        failed_attempts=attempts + 1,
                        last_outcome=f"failed: {type(error).__name__}",
                    )
                else:
                    write_state(
                        path, last_edition=due, failed_attempts=0,
                        last_outcome="succeeded",
                    )
        else:
            write_state(path)
        # Due deliveries retry on every wake, not just edition days.
        drain_safely()
        time.sleep(POLL_CAP_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
