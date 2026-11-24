# RSS ingestion pilot

The implementation starts from post-M02 main at `d9b8e69`.

| Step | Objective | Business value | Execution | Acceptance |
| --- | --- | --- | --- | --- |
| Registry | Limit fetching to approved RSS sources | Keep publisher and licensing decisions traceable | Record the direct feed URL, publisher, editorial category and licensing disposition in the M02 source registry | Pending and disabled sources are skipped |
| Fetch and parse | Retrieve RSS 2.0 metadata | Discover stories and preserve attribution | Run the one-shot ingestion command as the runtime role | HTTPS to public addresses, bounded reads, no redirects, safe XML parsing and conditional requests |
| Persist | Track articles, provenance and run outcomes | Handle repeated fetches without duplicate stories | Save normalized URLs, external IDs, publication times and source references | Duplicate records are avoided and a failed feed leaves other feeds eligible |
| Verify | Qualify the ingestion path | Keep CI independent of publisher uptime | Run the regression and disposable PostgreSQL checks | Fixtures cover repeated items, conditional responses, malformed XML and source failure isolation |

## Pilot registry candidates

| Publisher | Category | Feed | Disposition |
| --- | --- | --- | --- |
| RaceFans | Formula 1 | https://www.racefans.net/feed/ | Candidate for link discovery. Publisher directs article reuse requests to its contact form. |
| MacRumors | Technology and AI | https://feeds.macrumors.com/MacRumors-All | Candidate for link discovery. Publisher help recommends RSS for finding stories. |
| ESPN NASCAR | NASCAR | https://www.espn.com/espn/rss/nascar/news | Working feed. Automated private-digest use remains subject to feed terms review. |
| The Race | Formula 1 | https://www.the-race.com/rss/ | Backup. Check rights before any use beyond link discovery. |
| 9to5Mac | Technology and AI | https://9to5mac.com/feed/ | Backup. Check rights before any use beyond link discovery. |

The runtime ingests approved registry entries only. This change does not
activate publisher rows by default. RSS ingestion stores headline, link,
publication timestamp when available, source identifier and publisher
attribution. It does not retrieve article pages, store descriptions or
images, send data to a model, or deliver a digest.

## Run locally

Complete the [M02 database startup](M02.md), then rebuild with
`docker compose build api`. As the schema owner, register the feed and its
licensing disposition in `newspaper.sources`. Set `approval` to `approved`
after review. Use the final HTTPS feed URL because redirects are rejected.
Run one pass with `docker compose run --rm ingest`. The command reports
source IDs and outcomes and exits nonzero if a feed failed. Inspect the
`newspaper.ingestion_runs` records for failure codes. A subsequent pass
can retry failed sources without duplicating successful items.

## Local evidence

The application fetcher parsed 20 items each from RaceFans and MacRumors
on November 24, 2026 without writing publisher items to a database.
Fixture runs against disposable PostgreSQL passed. They covered
cross-publisher deduplication, repeated GUIDs, disabled-by-default source
selection, malformed feeds, and conditional requests.
