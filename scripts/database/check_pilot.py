"""Check that registration is repeatable and preserves existing source decisions."""

from sqlalchemy import select, update

from app.database import database_engine
from app.models import Source
from app.pilot import PILOT_SOURCES, register_sources

engine = database_engine(migration=True)
try:
    with engine.begin() as connection:
        for publisher, endpoint, category, _ in PILOT_SOURCES:
            row = connection.execute(
                select(Source.publisher, Source.category, Source.approval, Source.kind)
                .where(Source.endpoint == endpoint)
            ).one()
            assert tuple(row) == (publisher, category, "approved", "rss")

        yahoo = Source.endpoint == "https://sports.yahoo.com/nascar/rss/"
        connection.execute(update(Source).where(yahoo).values(approval="disabled"))
        assert register_sources(connection) == []
        assert connection.scalar(select(Source.approval).where(yahoo)) == "disabled"
finally:
    engine.dispose()
print("RSS pilot registration and existing source decisions passed")
