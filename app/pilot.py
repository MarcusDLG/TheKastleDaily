"""Register the personal RSS and Atom source registry."""

from sqlalchemy import update
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
    ("The Race", "https://www.the-race.com/rss/", "motorsport", DISCOVERY),
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
        "https://www.tomshardware.com/feeds.xml",
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
        "Martin Fowler",
        "https://martinfowler.com/feed.atom",
        "software_engineering",
        DISCOVERY + " Atom feed.",
    ),
    (
        "Pragmatic Engineer",
        "https://newsletter.pragmaticengineer.com/feed",
        "software_engineering",
        DISCOVERY,
    ),
    (
        "Netflix Tech Blog",
        "https://netflixtechblog.com/feed",
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
    (
        "Arduino Blog",
        "https://blog.arduino.cc/feed/",
        "maker_fabrication",
        DISCOVERY,
    ),
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
    (
        "Smitten Kitchen",
        "https://feeds.feedburner.com/smittenkitchen",
        "culinary",
        DISCOVERY,
    ),
    ("PetaPixel", "https://petapixel.com/feed/", "visual_craft", DISCOVERY),
    ("DPReview", "https://www.dpreview.com/feed/", "visual_craft", DISCOVERY),
    ("ServeTheHome", "https://www.servethehome.com/feed/", "homelab", DISCOVERY),
    ("Reef Builders", "https://reefbuilders.com/feed/", "life_systems", DISCOVERY),
    (
        "Aquarium Co-Op",
        "https://www.aquariumcoop.com/blogs/aquarium.atom",
        "life_systems",
        DISCOVERY,
    ),
    ("iRunFar", "https://www.irunfar.com/feed", "life_systems", DISCOVERY),
    (
        "Epic Gardening",
        "https://www.epicgardening.com/feed/",
        "life_systems",
        DISCOVERY,
    ),
    ("Farnam Street", "https://fs.blog/feed/", "life_systems", DISCOVERY),
)

# Verified as serving valid feeds but returning HTTP 403 to non-browser
# fetchers (Cloudflare bot gate; a residential retest with a browser
# user-agent also failed). Kept "pending"; clearing them needs a
# fetch-path change, not a different network.
PENDING_SOURCES = (
    (
        "Jayski's NASCAR",
        "https://www.jayski.com/feed/",
        "motorsport",
        "HTTP 403 from datacenter and residential fetchers.",
    ),
    (
        "Serious Eats",
        "https://www.seriouseats.com/feed",
        "culinary",
        "HTTP 403 from datacenter and residential fetchers.",
    ),
    (
        "All3DP",
        "https://all3dp.com/feed/",
        "maker_fabrication",
        "HTTP 403 from datacenter and residential fetchers.",
    ),
)

# Feeds that permanently moved; the fetcher refuses redirects by design.
# Their replacements are registered above. Existing rows for the old
# endpoints are flipped to "disabled" so ingestion history stays linked.
RETIRED_ENDPOINTS = frozenset(
    {
        "https://www.dpreview.com/feeds/news.xml",
        "https://www.the-race.com/feed/",
        "https://www.tomshardware.com/feeds/all",
    }
)


def register_sources(connection):
    connection.execute(
        update(Source)
        .where(Source.endpoint.in_(RETIRED_ENDPOINTS))
        .values(approval="disabled")
    )
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
