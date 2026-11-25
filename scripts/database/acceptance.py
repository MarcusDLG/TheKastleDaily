"""SQLite acceptance: migrations, drift, pilot registration, dedupe, persistence.

Creates a disposable database in a temporary directory and exercises the
full persistence path without Docker or network access. Run directly or via
scripts/database/acceptance.sh.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def run_alembic(database: Path, *args: str) -> None:
    env = os.environ.copy() | {"KASTLE_DB": str(database)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"alembic {' '.join(args)} failed:\n{result.stderr}")


FEED = b"""<rss version="2.0"><channel><item>
<guid>acceptance-1</guid><link>https://example.invalid/story</link>
<title>Acceptance story</title><pubDate>Tue, 24 Nov 2026 12:15:00 -0500</pubDate>
</item></channel></rss>"""


def main() -> int:
    with tempfile.TemporaryDirectory() as scratch:
        database = Path(scratch) / "kastle.db"

        # Migration idempotency and zero model drift.
        run_alembic(database, "upgrade", "head")
        run_alembic(database, "upgrade", "head")
        run_alembic(database, "check")

        os.environ["KASTLE_DB"] = str(database)
        from sqlalchemy import select

        from app.database import database_engine, session_factory
        from app.ingest import ingest_sources
        from app.models import ArticleSource, Source
        from app.pilot import PENDING_SOURCES, PILOT_SOURCES, register_sources
        from app.rss import FeedResponse

        engine = database_engine()
        try:
            with engine.begin() as connection:
                first = register_sources(connection)
                assert len(first) == len(PILOT_SOURCES) + len(PENDING_SOURCES), first
                second = register_sources(connection)
                assert second == [], "pilot registration must be idempotent"

            def stub_fetch(endpoint, etag, last_modified):
                if etag == "v1":
                    return FeedResponse(None, "v1", None)
                return FeedResponse(FEED, "v1", None)

            sessions = session_factory(engine)
            results = ingest_sources(sessions, fetch=stub_fetch)
            assert len(results) == len(PILOT_SOURCES), results
            with sessions() as session:
                rows = session.execute(
                    select(ArticleSource.external_id).where(
                        ArticleSource.external_id == "acceptance-1"
                    )
                ).all()
                assert len(rows) == len(PILOT_SOURCES), "one observation per approved source for the shared guid"

            # Conditional refetch (304) stores nothing new.
            results = ingest_sources(sessions, fetch=stub_fetch)
            with sessions() as session:
                total = session.execute(select(ArticleSource.id)).all()
                assert len(total) == len(PILOT_SOURCES), "a not-modified pass must not duplicate rows"

            # Provenance survives an engine restart.
            engine.dispose()
            engine = database_engine()
            sessions = session_factory(engine)
            with sessions() as session:
                publishers = session.execute(select(Source.publisher)).all()
                assert len(publishers) == len(PILOT_SOURCES) + len(PENDING_SOURCES), publishers
        finally:
            engine.dispose()

    print("SQLite acceptance passed: migrations, drift, pilot, dedupe, persistence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
