"""SQLite persistence for the newspaper pipeline.

One file, one writer. The database path comes from KASTLE_DB (default
./data/kastle.db). WAL mode and foreign keys are enabled per connection.
"""

import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def database_path() -> str:
    configured = os.environ.get("KASTLE_DB", "data/kastle.db")
    if configured != ":memory:":
        Path(configured).parent.mkdir(parents=True, exist_ok=True)
    return configured


@event.listens_for(Engine, "connect")
def _set_pragmas(connection, _record):
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def database_engine():
    path = database_path()
    if path == ":memory:":
        # One shared in-memory database for tests instead of one per pooled connection.
        from sqlalchemy.pool import StaticPool

        return create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            hide_parameters=True,
        )
    return create_engine(f"sqlite+pysqlite:///{path}", hide_parameters=True)


def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
