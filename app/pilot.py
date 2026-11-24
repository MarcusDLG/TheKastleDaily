"""Register the personal RSS pilot feeds using the schema owner's credentials."""

from sqlalchemy.dialects.postgresql import insert

from app.database import database_engine
from app.models import Source

PILOT_SOURCES = (
    (
        "Yahoo Sports NASCAR",
        "https://sports.yahoo.com/nascar/rss/",
        "nascar",
        "Personal feed discovery. Attribute Yahoo Sports and retain its article links.",
    ),
    (
        "RaceFans",
        "https://www.racefans.net/feed/",
        "formula_1",
        "Personal feed discovery with publisher attribution.",
    ),
    (
        "MacRumors",
        "https://feeds.macrumors.com/MacRumors-All",
        "technology_ai",
        "Personal feed discovery with publisher attribution.",
    ),
    (
        "Ars Technica",
        "https://arstechnica.com/feed/",
        "technology_ai",
        "Personal feed discovery via the public publisher feed with attribution.",
    ),
)


def register_sources(connection):
    rows = [
        {
            "kind": "rss",
            "publisher": publisher,
            "endpoint": endpoint,
            "category": category,
            "licensing_note": note,
            "approval": "approved",
        }
        for publisher, endpoint, category, note in PILOT_SOURCES
    ]
    return connection.execute(
        insert(Source)
        .values(rows)
        .on_conflict_do_nothing(index_elements=[Source.endpoint])
        .returning(Source.publisher)
    ).scalars().all()


def main():
    engine = database_engine(migration=True)
    try:
        with engine.begin() as connection:
            added = register_sources(connection)
    finally:
        engine.dispose()
    print(f"Added {len(added)} pilot sources. Existing registry entries were preserved.")


if __name__ == "__main__":
    main()
