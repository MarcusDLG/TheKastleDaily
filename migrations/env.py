from alembic import context
from sqlalchemy import text

from app.database import SCHEMA, database_engine
from app.models import Base


def include_name(name, type_, parent_names):
    return type_ != "schema" or name == SCHEMA


def run_migrations():
    engine = database_engine(migration=True)
    try:
        with engine.begin() as connection:
            # Serialize migration and provisioning transactions.
            connection.execute(text("SELECT pg_advisory_xact_lock(864317)"))
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                version_table_schema=SCHEMA,
                include_schemas=True,
                include_name=include_name,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Connect as the migration role to run Alembic")
run_migrations()
