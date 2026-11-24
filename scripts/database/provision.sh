#!/bin/sh
set -eu

: "${POSTGRES_PASSWORD:?Set the bootstrap database password}"
: "${MIGRATION_DB_PASSWORD:?Set the migration database password}"
: "${APP_DB_PASSWORD:?Set the application database password}"

for value in "$POSTGRES_PASSWORD" "$MIGRATION_DB_PASSWORD" "$APP_DB_PASSWORD"; do
    if [ "${#value}" -lt 24 ]; then
        echo "Each database password must be at least 24 characters." >&2
        exit 1
    fi
done
if [ "$POSTGRES_PASSWORD" = "$MIGRATION_DB_PASSWORD" ] ||
   [ "$POSTGRES_PASSWORD" = "$APP_DB_PASSWORD" ] ||
   [ "$MIGRATION_DB_PASSWORD" = "$APP_DB_PASSWORD" ]; then
    echo "Use three distinct database passwords." >&2
    exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"
psql -X -w -h db -U kastle_bootstrap -d kastle_daily -v ON_ERROR_STOP=1 <<'SQL'
\getenv migration_password MIGRATION_DB_PASSWORD
\getenv application_password APP_DB_PASSWORD

BEGIN;
SELECT pg_advisory_xact_lock(864317);
SET LOCAL password_encryption = 'scram-sha-256';
-- Suppress server statement logging while setting role credentials.
SET LOCAL log_statement = 'none';
SET LOCAL log_min_duration_statement = -1;
SET LOCAL log_min_error_statement = 'panic';

SELECT 'CREATE ROLE kastle_migrator'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kastle_migrator') \gexec
SELECT 'CREATE ROLE kastle_app'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kastle_app') \gexec
ALTER ROLE kastle_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'migration_password';
ALTER ROLE kastle_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'application_password';

REVOKE ALL ON DATABASE kastle_daily, postgres, template1 FROM PUBLIC;
GRANT CONNECT ON DATABASE kastle_daily TO kastle_migrator, kastle_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS newspaper AUTHORIZATION kastle_migrator;
ALTER SCHEMA newspaper OWNER TO kastle_migrator;
REVOKE ALL ON SCHEMA newspaper FROM PUBLIC;
GRANT USAGE ON SCHEMA newspaper TO kastle_app;

ALTER ROLE kastle_migrator IN DATABASE kastle_daily SET timezone TO 'UTC';
ALTER ROLE kastle_app IN DATABASE kastle_daily SET timezone TO 'UTC';
COMMIT;
SQL
