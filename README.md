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
acceptance, including 73 automated regression tests.

The physical Kindle proof of concept passed 31 manual tests.

Persistence now uses SQLite in a single long-running worker
container; PostgreSQL, the FastAPI service and one-shot Compose
jobs were removed in the simplification pass (see
[Architecture](docs/ARCHITECTURE.md)). The M02 PostgreSQL
runbook is retained for history only.

Full Master Execution Plan Revision 4.0 reconciliation
remains outstanding.

## Technology

- Python 3.12.
- SQLite (single file, WAL mode) with SQLAlchemy and Alembic.
- Docker and Docker Compose.
- GitHub Actions and GHCR.
- Synology DS220+ target host.
- RSS, YouTube Data API and OpenAI API.
- EPUB and Amazon Send to Kindle.
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
No secrets are needed for local development or CI.

Run the pipeline once end to end against a local database:

    python -m app.schedule --once

Run the worker container (writes editions under `data/`):

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
- [EPUB edition build](docs/EPUB_EDITION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [External integrations](docs/INTEGRATIONS.md)
- [Testing](docs/TESTING.md)

## Authorization

Merging, container publication and NAS deployment require
explicit project owner approval.
