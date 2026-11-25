from alembic import context

from app.database import database_engine
from app.models import Base


def run_migrations():
    engine = database_engine()
    try:
        with engine.begin() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migration mode is not supported")
run_migrations()
