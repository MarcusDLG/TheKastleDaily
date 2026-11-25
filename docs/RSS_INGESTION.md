# RSS ingestion pilot

The implementation starts from post-M02 main at `d9b8e69`.

| Step | Objective | Business value | Execution | Acceptance |
| --- | --- | --- | --- | --- |
| Registry | Limit fetching to approved RSS sources | Keep publisher and licensing decisions traceable | Record the direct feed URL, publisher, editorial category and licensing disposition in the M02 source registry | Pending and disabled sources are skipped |
| Fetch and parse | Retrieve RSS 2.0 metadata | Discover stories and preserve attribution | Run the one-shot ingestion command as the runtime role | HTTPS to public addresses, bounded reads, no redirects, safe XML parsing and conditional requests |
| Persist | Track articles, provenance and run outcomes | Handle repeated fetches without duplicate stories | Save normalized URLs, external IDs, publication times and source references | Duplicate records are avoided and a failed feed leaves other feeds eligible |
| Verify | Qualify the ingestion path | Keep CI independent of publisher uptime | Run the regression and SQLite persistence checks | Fixtures cover repeated items, conditional responses, malformed XML and source failure isolation |

## Personal pilot registry

| Publisher | Category | Feed | Disposition |
| --- | --- | --- | --- |
| Yahoo Sports NASCAR | NASCAR | https://sports.yahoo.com/nascar/rss/ | Attributed headline and link discovery. Yahoo aggregates coverage from multiple outlets. |
| RaceFans | Formula 1 | https://www.racefans.net/feed/ | Open-wheel coverage and publisher attribution. |
| MacRumors | Technology and AI | https://feeds.macrumors.com/MacRumors-All | Apple coverage and publisher attribution. |
| Ars Technica | Technology and AI | https://arstechnica.com/feed/ | Broader technology coverage from the supplied Tech OPML, using the publisher's direct HTTPS feed. |
| iRacing | Sim Racing | https://www.iracing.com/feed/ | Sim racing updates and events. |
| Raspberry Pi | Maker and Radio | https://www.raspberrypi.com/news/feed/ | Maker and hardware project coverage. |

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
