# The Kastle Daily

A self-hosted, personalized daily newspaper designed for
delivery to Amazon Kindle.

The application will collect approved news sources,
rank relevant stories, generate evidence-backed editorial
content and deliver one daily EPUB edition containing
approximately 15 articles.

## Project status

M00 initialization implementation and feasibility assessments
were accepted and squash merged in PR #1 at `b0acc98`.

The security pipeline has passed local and remote CI
acceptance, including 71 automated regression tests.

The physical Kindle proof of concept passed 31 manual tests.

M02 adds PostgreSQL persistence and Alembic migrations.

Full Master Execution Plan Revision 4.0 reconciliation
remains outstanding.

## Technology

- Python 3.12 and FastAPI.
- PostgreSQL 17.
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

To start the local stack, create `.env` from `.env.example`
for a fresh workspace and set three distinct random passwords.
Run `openssl rand -hex 32` separately for each password. For an
existing M00 volume, retain its current bootstrap password and follow
the existing-volume notes in the [M02 runbook](docs/M02.md).

```sh
docker compose build api
docker compose run --rm provision
docker compose run --rm migrate
docker compose up -d api
curl --fail http://127.0.0.1:8765/healthz
curl --fail http://127.0.0.1:8765/readyz
docker compose down
```

Run the disposable PostgreSQL integration checks with
`bash scripts/database/acceptance.sh`.

## Documentation

- [Project status](docs/PROJECT_STATUS.md)
- [M02 plan and database runbook](docs/M02.md)
- [RSS ingestion pilot](docs/RSS_INGESTION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [External integrations](docs/INTEGRATIONS.md)
- [Testing](docs/TESTING.md)

## Authorization

Merging, container publication and NAS deployment require
explicit project owner approval.
