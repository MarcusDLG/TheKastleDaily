"""PostgreSQL connections for the runtime and the migration command."""

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

SCHEMA = "newspaper"


def database_engine(*, migration: bool = False):
    user, password_variable = (
        ("kastle_migrator", "MIGRATION_DB_PASSWORD")
        if migration
        else ("kastle_app", "APP_DB_PASSWORD")
    )
    password = os.environ.get(password_variable)
    if not password:
        raise ValueError(f"Set {password_variable} to configure the database")
    url = URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database="kastle_daily",
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"}
        if not migration
        else {"connect_timeout": 5},
        hide_parameters=True,
    )


def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
