#!/bin/sh
# Create the non-privileged RUNTIME role for the app (feature 006 multi-tenancy).
#
# Postgres runs every *.sh/*.sql in /docker-entrypoint-initdb.d once, on first DB
# init. POSTGRES_USER (the superuser/owner, e.g. "wcl") owns the tables and runs
# Alembic. This script adds a SECOND role the FastAPI app connects as at runtime —
# NOT a superuser, NOT a table owner, and WITHOUT BYPASSRLS — so row-level security
# actually constrains it (research R4). Table-level SELECT/INSERT/UPDATE/DELETE
# grants are applied by migration 0004_rls, keeping RLS + grants together.
set -eu

APP_DB_USER="${APP_DB_USER:-wcl_app}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:-wcl_app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
    CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END
\$\$;

GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_USER};
GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};
-- Future tables created by the owner should be usable by the runtime role; RLS still
-- applies. Per-table DML grants live in migration 0004_rls.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
SQL
