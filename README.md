# The Kastle Daily

A self-hosted, personalized daily newspaper designed for
delivery to Amazon Kindle.

The application collects approved news sources,
ranks relevant stories, generates evidence-backed editorial
content and delivers one daily EPUB edition containing
approximately 15 articles.

## Project status

M00 initialization implementation and feasibility assessments
were accepted and squash merged in PR #1 at `b0acc98`.

The security pipeline has passed local and remote CI
acceptance, including 73 automated regression tests at
assessment; the suite has since grown to 129 tests.

The physical Kindle proof of concept passed 31 manual tests.

The core pipeline is implemented end to end. A live run on
2026-11-25 ingested feeds, selected and drafted stories,
built and validated an edition, and delivered it to the
Kindle over SMTP. OpenAI model generation and NAS deployment
remain unqualified; formal EPUBCheck validation of the
pipeline build is still outstanding.

Persistence uses SQLite in a single long-running worker
container; PostgreSQL, the FastAPI service and one-shot
Compose jobs were removed in the simplification pass (see
[Architecture](docs/ARCHITECTURE.md)). The M02 PostgreSQL
runbook is retained for history only.

Full Master Execution Plan Revision 4.0 reconciliation
remains outstanding.

## Architecture

One `worker` container runs `python -m app.schedule`. It
wakes every fifteen minutes and, once the configured edition
time (07:00 America/New_York) has passed, executes the
pipeline once for that calendar day, with at most three
attempts:

1. Alembic migrations.
2. Source registration and RSS/Atom ingestion.
3. Editorial selection: configured section weights via
   largest-remainder rounding, one reserved
   sim-racing/maker/radio slot, coverage-floor gate.
4. Evidence acquisition (bounded HTTPS fetch, trafilatura
   extraction, `og:image` story photos under
   `editions/photos/`) and drafting. The default template
   generator needs no credentials; setting `OPENAI_API_KEY`
   switches to an OpenAI adapter with a per-edition cost cap.
5. EPUB edition build with a generated masthead cover and
   contract validation, persisted beside the database at
   `editions/<edition-date>.epub`.
6. Delivery: a persistent SMTP outbox submits the edition to
   the configured Kindle address with bounded retries;
   ambiguous submissions are held for manual reconciliation.

SQLite lives on a named volume at `/data/kastle.db` (WAL
mode, single writer); backup is a file copy. Rendered EPUBs
and story photos are rebuildable artifacts and excluded
from the backup contract. Scheduler state and the health heartbeat live in
`run-state.json` beside the database. The container
publishes no ports and runs non-root with a read-only root
filesystem.

## Technology

- Python 3.12, standard library first.
- SQLite (single file, WAL mode) with SQLAlchemy and Alembic.
- feedparser for ingestion; trafilatura for evidence
  extraction.
- Docker and Docker Compose.
- GitHub Actions and GHCR.
- Synology DS220+ target host.
- RSS and Atom feeds, YouTube Data API (supplemental) and
  OpenAI API.
- EPUB and Amazon Send to Kindle over SMTP.
- Future web administration and MCP integration.

Instagram is excluded.

## Local development

Use Python 3.12.

Create and activate a virtual environment:

    python3.12 -m venv .venv
    source .venv/bin/activate

Install locked development dependencies:

    python -m pip install \
      --require-hashes \
      --only-binary=:all: \
      -r requirements-dev.txt

Run automated regression:

    python -m pytest

Create `.env` from `.env.example` for any real deployment.
SMTP and Kindle variables enable delivery; `OPENAI_API_KEY`
enables model drafting. Empty values keep those stages
inert. No secrets are needed for local development or CI.

Run the pipeline once end to end against a local database:

    python -m app.schedule --once

Run the worker container (writes the database and editions
under the `kastle-data` volume):

```sh
docker compose build
docker compose up -d
docker compose down
```

Run the SQLite persistence and ingestion acceptance checks with
`bash scripts/database/acceptance.sh`.

## Documentation

- [Project status](docs/PROJECT_STATUS.md)
- [M02 plan and database runbook](docs/M02.md) (superseded)
- [RSS ingestion pilot](docs/RSS_INGESTION.md)
- [Editorial selection](docs/EDITORIAL_SELECTION.md)
- [Editorial drafting](docs/EDITORIAL_DRAFTING.md)
- [EPUB edition build](docs/EPUB_EDITION.md)
- [Delivery outbox](docs/DELIVERY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [External integrations](docs/INTEGRATIONS.md)
- [Testing](docs/TESTING.md)

## Authorization

Merging, container publication and NAS deployment require
explicit project owner approval.
