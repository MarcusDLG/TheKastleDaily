# The Kastle Daily

A self-hosted, personalized daily newspaper designed for
delivery to Amazon Kindle.

The application will collect approved news sources,
rank relevant stories, generate evidence-backed editorial
content and deliver one daily EPUB edition containing
approximately 15 articles.

## Project status

M00 initialization implementation and feasibility assessments
are complete. Final pull request acceptance remains pending.

The security pipeline has passed local and remote CI
acceptance, including 71 automated regression tests.

The physical Kindle proof of concept passed 31 manual tests.

M02 persistence and database migrations are the next planned
implementation workstream.

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

For local container smoke testing, copy .env.example to .env
and configure a strong database password.

    docker compose up --build -d

Check the local health endpoint:

    curl http://127.0.0.1:8765/healthz

Stop the local environment:

    docker compose down

Do not remove persistent database volumes unless explicitly
intended.

No production NAS deployment is authorized.

## Documentation

- [Project status](docs/PROJECT_STATUS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [External integrations](docs/INTEGRATIONS.md)
- [Testing](docs/TESTING.md)

## Authorization

Merging, container publication and NAS deployment require
explicit project owner approval.
