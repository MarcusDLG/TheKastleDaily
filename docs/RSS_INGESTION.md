# RSS ingestion pilot

The implementation starts from post-M02 main at `d9b8e69`.

| Step | Objective | Business value | Execution | Acceptance |
| --- | --- | --- | --- | --- |
| Registry | Limit fetching to approved RSS sources | Keep publisher and licensing decisions traceable | Record the direct feed URL, publisher, editorial category and licensing disposition in the M02 source registry | Pending and disabled sources are skipped |
| Fetch and parse | Retrieve RSS 2.0 and Atom metadata | Discover stories and preserve attribution | Run the one-shot ingestion command as the runtime role | HTTPS to public addresses, bounded reads, no redirects, DTD rejection and tolerant feedparser parsing, conditional requests |
| Persist | Track articles, provenance and run outcomes | Handle repeated fetches without duplicate stories | Save normalized URLs, external IDs, publication times and source references | Duplicate records are avoided and a failed feed leaves other feeds eligible |
| Verify | Qualify the ingestion path | Keep CI independent of publisher uptime | Run the regression and SQLite persistence checks | Fixtures cover repeated items, conditional responses, malformed XML and source failure isolation |

## Personal source registry

The registry mirrors the eleven editorial sections in
`config/editorial.yaml`. Each feed was verified to serve a valid
RSS 2.0 or Atom document over HTTPS.

| Publisher | Category | Feed | Disposition |
| --- | --- | --- | --- |
| Yahoo Sports NASCAR | Motorsport | https://sports.yahoo.com/nascar/rss/ | Personal feed discovery with publisher attribution. Yahoo aggregates coverage from multiple outlets. |
| RaceFans | Motorsport | https://www.racefans.net/feed/ | Personal feed discovery with publisher attribution. |
| The Race | Motorsport | https://www.the-race.com/rss/ | Personal feed discovery with publisher attribution. |
| Sportscar365 | Motorsport | https://sportscar365.com/feed/ | Personal feed discovery with publisher attribution. |
| iRacing | Sim Racing | https://www.iracing.com/feed/ | Personal feed discovery with publisher attribution. |
| Traxion | Sim Racing | https://traxion.gg/feed/ | Personal feed discovery with publisher attribution. |
| MacRumors | Technology and AI | https://feeds.macrumors.com/MacRumors-All | Personal feed discovery with publisher attribution. |
| Ars Technica | Technology and AI | https://arstechnica.com/feed/ | Personal feed discovery with publisher attribution. |
| The Verge | Technology and AI | https://www.theverge.com/rss/index.xml | Personal feed discovery with publisher attribution. Atom feed. |
| Tom's Hardware | Technology and AI | https://www.tomshardware.com/feeds.xml | Personal feed discovery with publisher attribution. |
| Simon Willison | Software Engineering | https://simonwillison.net/atom/everything/ | Personal feed discovery with publisher attribution. Atom feed. |
| Martin Fowler | Software Engineering | https://martinfowler.com/feed.atom | Personal feed discovery with publisher attribution. Atom feed. |
| Pragmatic Engineer | Software Engineering | https://newsletter.pragmaticengineer.com/feed | Personal feed discovery with publisher attribution. |
| Netflix Tech Blog | Software Engineering | https://netflixtechblog.com/feed | Personal feed discovery with publisher attribution. |
| Raspberry Pi | Maker and Fabrication | https://www.raspberrypi.com/news/feed/ | Personal feed discovery with publisher attribution. |
| Hackaday | Maker and Fabrication | https://hackaday.com/feed/ | Personal feed discovery with publisher attribution. |
| Prusa3D | Maker and Fabrication | https://blog.prusa3d.com/feed/ | Personal feed discovery with publisher attribution. |
| Arduino Blog | Maker and Fabrication | https://blog.arduino.cc/feed/ | Personal feed discovery with publisher attribution. |
| RTL-SDR | Radio and Comms | https://www.rtl-sdr.com/feed/ | Personal feed discovery with publisher attribution. |
| Meshtastic | Radio and Comms | https://meshtastic.org/blog/rss.xml | Personal feed discovery with publisher attribution. |
| Spaceflight Now | Space | https://spaceflightnow.com/feed/ | Personal feed discovery with publisher attribution. |
| NASASpaceflight | Space | https://www.nasaspaceflight.com/feed/ | Personal feed discovery with publisher attribution. |
| Just One Cookbook | Culinary | https://www.justonecookbook.com/feed/ | Personal feed discovery with publisher attribution. |
| Smitten Kitchen | Culinary | https://feeds.feedburner.com/smittenkitchen | Personal feed discovery with publisher attribution. |
| PetaPixel | Visual Craft | https://petapixel.com/feed/ | Personal feed discovery with publisher attribution. |
| DPReview | Visual Craft | https://www.dpreview.com/feed/ | Personal feed discovery with publisher attribution. |
| ServeTheHome | Home Lab | https://www.servethehome.com/feed/ | Personal feed discovery with publisher attribution. |
| Reef Builders | Life Systems | https://reefbuilders.com/feed/ | Personal feed discovery with publisher attribution. |
| Aquarium Co-Op | Life Systems | https://www.aquariumcoop.com/blogs/aquarium.atom | Personal feed discovery with publisher attribution. Atom feed. |
| iRunFar | Life Systems | https://www.irunfar.com/feed | Personal feed discovery with publisher attribution. |
| Epic Gardening | Life Systems | https://www.epicgardening.com/feed/ | Personal feed discovery with publisher attribution. |
| Farnam Street | Life Systems | https://fs.blog/feed/ | Personal feed discovery with publisher attribution. |

Three additional candidates are registered as `pending` because they
return HTTP 403 to non-browser fetchers (Jayski's NASCAR, Serious Eats,
All3DP). A residential-network retest with a browser user-agent also
failed, so the block is a bot gate rather than an IP restriction;
clearing them needs a fetch-path change. Pending sources are never
fetched.

When a publisher moves its feed, register the new URL as a separate
source row and let registration flip the old endpoint to `disabled` —
the fetcher rejects redirects by design, and retirement keeps ingestion
history linked to the endpoint that produced it.

The runtime ingests approved registry entries only. The registration command explicitly opts the local database into the pilot.
It leaves any existing registry row and approval decision intact. RSS ingestion stores headline, link,
publication timestamp when available, source identifier and publisher
attribution. It does not retrieve article pages, store descriptions or
images, send data to a model, or deliver a digest.

## Run locally

No Docker or secrets are required. Run the full pass once (migrations,
registration, ingestion and selection):

```sh
python -m app.schedule --once
```

or stage by stage:

```sh
python -m alembic upgrade head
python -m app.pilot
python -m app.ingest
python -m app.selection
```

The database defaults to `./data/kastle.db` (override with `KASTLE_DB`).
Registration is idempotent: run it again to add any missing pilot sources.
Use the final HTTPS feed URL when registering other sources because the
importer rejects redirects. The ingestion command reports
source IDs and outcomes and exits nonzero if a feed failed. Inspect the
`ingestion_runs` records for failure codes. A subsequent pass
can retry failed sources without duplicating successful items.

## Local evidence

The application fetcher parsed 20 items each from RaceFans and MacRumors
on November 24, 2026 without writing publisher items to a database.
Fixture runs against disposable PostgreSQL passed. They covered
cross-publisher deduplication, repeated GUIDs, disabled-by-default source
selection, malformed feeds, and conditional requests.
