#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

# Keep this run independent of the developer's .env, images and volumes.
project="kastle-m02-$$"
export POSTGRES_PASSWORD="$(openssl rand -hex 32)"
export MIGRATION_DB_PASSWORD="$(openssl rand -hex 32)"
export APP_DB_PASSWORD="$(openssl rand -hex 32)"
export KASTLE_APP_IMAGE="$project:acceptance"
compose=(docker compose --env-file /dev/null -p "$project")

cleanup() {
    if [[ -n "${api:-}" ]]; then
        docker rm -f "$api" >/dev/null
    fi
    "${compose[@]}" down --volumes --remove-orphans
}
trap cleanup EXIT

"${compose[@]}" config --quiet
"${compose[@]}" build api
"${compose[@]}" up -d --wait --wait-timeout 90 db
"${compose[@]}" run --rm -T provision
"${compose[@]}" run --rm -T provision
"${compose[@]}" run --rm -T migrate
"${compose[@]}" run --rm -T migrate
"${compose[@]}" run --rm -T migrate alembic check
"${compose[@]}" run --rm -T migrate alembic downgrade base

api=$("${compose[@]}" run -d --no-deps api)
docker exec -i "$api" python - 503 < scripts/database/check_readiness.py
"${compose[@]}" run --rm -T migrate
"${compose[@]}" run --rm -T migrate alembic check
"${compose[@]}" run --rm -T ingest
"${compose[@]}" exec -T db sh -ec '
    export PGPASSWORD="$POSTGRES_PASSWORD"
    psql -X -w -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
' <<'SQL'
INSERT INTO newspaper.sources (kind, endpoint, publisher, category, licensing_note, approval)
VALUES ('rss', 'https://example.invalid/feed', 'Fixture', 'formula_1', 'Test only', 'approved');
SQL
docker exec -i "$api" python - 200 < scripts/database/check_readiness.py
docker exec -i "$api" python - < scripts/database/check_persistence.py
"${compose[@]}" exec -T db sh -ec '
    export PGPASSWORD="$POSTGRES_PASSWORD"
    psql -X -w -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
' <<'SQL'
INSERT INTO newspaper.sources (kind, endpoint, publisher, category, licensing_note, approval)
VALUES
    ('rss', 'https://example.invalid/second-feed', 'Second', 'nascar', 'Test only', 'approved'),
    ('rss', 'https://example.invalid/bad-feed', 'Bad', 'nascar', 'Test only', 'approved'),
    ('rss', 'https://example.invalid/pending', 'Pending', 'nascar', 'Test only', 'pending'),
    ('youtube', 'https://example.invalid/channel', 'Video', 'nascar', 'Test only', 'approved');
SQL
docker exec -i "$api" python - < scripts/database/check_ingestion.py
"${compose[@]}" run --rm -T migrate python -m app.pilot
"${compose[@]}" run --rm -T migrate python - < scripts/database/check_pilot.py
"${compose[@]}" exec -T db sh -ec '
    export PGPASSWORD="$POSTGRES_PASSWORD"
    psql -X -w -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
' <<'SQL'
WITH source AS (
    SELECT id FROM newspaper.sources WHERE endpoint = 'https://www.iracing.com/feed/'
), run AS (
    INSERT INTO newspaper.ingestion_runs (source_id, status)
    SELECT id, 'succeeded' FROM source RETURNING id, source_id
), article AS (
    INSERT INTO newspaper.articles (canonical_url, title)
    VALUES ('https://example.invalid/sim', 'Sim racing fixture') RETURNING id
)
INSERT INTO newspaper.article_sources
    (article_id, source_id, ingestion_run_id, external_id, source_url, attributed_to)
SELECT article.id, run.source_id, run.id, 'fixture-sim', 'https://example.invalid/sim', 'iRacing'
FROM article CROSS JOIN run;
SQL
"${compose[@]}" run --rm -T select-stories | python3 -c '
import json
import sys
plan = json.load(sys.stdin)
assert plan["coverage_floor_met"] is True
assert plan["coverage"]["sim_racing"]["selected"] == 1
assert any(story["reserved"] and story["title"] == "Sim racing fixture" for story in plan["stories"])
print("Editorial selection and reserved coverage passed")
'
