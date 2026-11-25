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
from datetime import UTC, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

POLL_CAP_SECONDS = 900
MAX_ATTEMPTS_PER_EDITION = 3


def edition_config(config_path="config/editorial.yaml"):
    config = yaml.safe_load(Path(config_path).read_text())
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
    """Migrate, register sources, ingest, and select today's plan."""
    from alembic.config import main as alembic_main

    from app.database import database_engine, session_factory
    from app.ingest import ingest_sources
    from app.pilot import register_sources
    from app.selection import build_plan

    alembic_main(argv=["upgrade", "head"])
    engine = database_engine()
    try:
        with engine.begin() as connection:
            register_sources(connection)
        ingest_sources(session_factory(engine))
        print(json.dumps(build_plan(), default=str, indent=2))
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

    if args.once:
        run_pipeline()
        write_state(path, last_outcome="manual")
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
        time.sleep(POLL_CAP_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
