"""Register the personal RSS and Atom source registry."""

from sqlalchemy.dialects.sqlite import insert

from app.database import database_engine
from app.models import Source

DISCOVERY = "Personal feed discovery with publisher attribution."

PILOT_SOURCES = (
    (
        "Yahoo Sports NASCAR",
        "https://sports.yahoo.com/nascar/rss/",
        "motorsport",
        DISCOVERY + " Yahoo aggregates coverage from multiple outlets.",
    ),
    ("RaceFans", "https://www.racefans.net/feed/", "motorsport", DISCOVERY),
    ("The Race", "https://www.the-race.com/feed/", "motorsport", DISCOVERY),
    ("Sportscar365", "https://sportscar365.com/feed/", "motorsport", DISCOVERY),
    ("iRacing", "https://www.iracing.com/feed/", "sim_racing", DISCOVERY),
    ("Traxion", "https://traxion.gg/feed/", "sim_racing", DISCOVERY),
    (
        "MacRumors",
        "https://feeds.macrumors.com/MacRumors-All",
        "technology_ai",
        DISCOVERY,
    ),
    ("Ars Technica", "https://arstechnica.com/feed/", "technology_ai", DISCOVERY),
    (
        "The Verge",
        "https://www.theverge.com/rss/index.xml",
        "technology_ai",
        DISCOVERY,
    ),
    (
        "Tom's Hardware",
        "https://www.tomshardware.com/feeds/all",
        "technology_ai",
        DISCOVERY,
    ),
    (
        "Simon Willison",
        "https://simonwillison.net/atom/everything/",
        "software_engineering",
        DISCOVERY,
    ),
    (
        "Raspberry Pi",
        "https://www.raspberrypi.com/news/feed/",
        "maker_fabrication",
        DISCOVERY,
    ),
    ("Hackaday", "https://hackaday.com/feed/", "maker_fabrication", DISCOVERY),
    ("Prusa3D", "https://blog.prusa3d.com/feed/", "maker_fabrication", DISCOVERY),
    ("RTL-SDR", "https://www.rtl-sdr.com/feed/", "radio_comms", DISCOVERY),
    ("Meshtastic", "https://meshtastic.org/blog/rss.xml", "radio_comms", DISCOVERY),
    ("Spaceflight Now", "https://spaceflightnow.com/feed/", "space", DISCOVERY),
    ("NASASpaceflight", "https://www.nasaspaceflight.com/feed/", "space", DISCOVERY),
    (
        "Just One Cookbook",
        "https://www.justonecookbook.com/feed/",
        "culinary",
        DISCOVERY,
    ),
    ("PetaPixel", "https://petapixel.com/feed/", "visual_craft", DISCOVERY),
    ("DPReview", "https://www.dpreview.com/feeds/news.xml", "visual_craft", DISCOVERY),
    ("ServeTheHome", "https://www.servethehome.com/feed/", "homelab", DISCOVERY),
    ("Reef Builders", "https://reefbuilders.com/feed/", "life_systems", DISCOVERY),
    (
        "Aquarium Co-Op",
        "https://www.aquariumcoop.com/blogs/aquarium.atom",
        "life_systems",
        DISCOVERY,
    ),
)

# Verified as serving valid feeds but blocked to datacenter fetchers (HTTP 403).
# Retest from the residential NAS connection before flipping to "approved".
PENDING_SOURCES = (
    (
        "Jayski's NASCAR",
        "https://www.jayski.com/feed/",
        "motorsport",
        "Pending NAS-side retest; datacenter fetch returned HTTP 403.",
    ),
    (
        "Serious Eats",
        "https://www.seriouseats.com/feed",
        "culinary",
        "Pending NAS-side retest; datacenter fetch returned HTTP 403.",
    ),
    (
        "All3DP",
        "https://all3dp.com/feed/",
        "maker_fabrication",
        "Pending NAS-side retest; datacenter fetch returned HTTP 403.",
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
            "approval": approval,
        }
        for group, approval in (
            (PILOT_SOURCES, "approved"),
            (PENDING_SOURCES, "pending"),
        )
        for publisher, endpoint, category, note in group
    ]
    return connection.execute(
        insert(Source)
        .values(rows)
        .on_conflict_do_nothing(index_elements=[Source.endpoint])
        .returning(Source.publisher)
    ).scalars().all()


def main():
    engine = database_engine()
    try:
        with engine.begin() as connection:
            added = register_sources(connection)
    finally:
        engine.dispose()
    print(f"Added {len(added)} pilot sources. Existing registry entries were preserved.")


if __name__ == "__main__":
    main()
