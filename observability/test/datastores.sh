#!/usr/bin/env bash
# Feature 058 (sc-417, sc-418, sc-419, sc-420) on a seeded stack: the app's db (migrated, with the
# monitoring role, an HNSW index with rows), Redis, Alloy and the backends. Asserts values, not
# presence: the top statement by total time is the seeded slow one, the vector index size equals
# pg_relation_size, Redis's hit ratio equals the hits and misses made, the slow-query line in Loki
# carries the trace id of the traced statement (and that trace is in Tempo), seeded secrets are
# masked, lock waits and autovacuum are logged, D9-D11 load and every query is valid, and the
# added series stay inside the budget.
#   observability/test/datastores.sh        (KEEP=1 leaves the stack up)
export DB_PORT="${DB_PORT:-24432}" REDIS_PORT="${REDIS_PORT:-24379}"
# Throwaway credentials for this run's database (the db service reads them from the shell).
rnd() { od -An -N12 -tx1 /dev/urandom | tr -d ' \n'; }
export POSTGRES_USER=wcl POSTGRES_DB=wcl POSTGRES_PASSWORD="owner$(rnd)" \
  APP_DB_USER=wcl_app APP_DB_PASSWORD="app$(rnd)" PG_MONITOR_USER=wcl_monitor PG_MONITOR_PASSWORD="mon$(rnd)"
source "$(dirname "$0")/lib.sh"
trap stack_down EXIT

dc up -d --wait db redis docker-proxy cadvisor alloy "${BACKENDS[@]}" grafana >/dev/null
wait_ready

# The schema as the app gets it (migrations as the owner, 0022 creates the monitoring role).
if (cd "$REPO_ROOT" && env -i HOME="$HOME" PATH="$PATH" WCL_LOAD_DOTENV=0 \
    APP_DB_USER="$APP_DB_USER" APP_DB_PASSWORD="$APP_DB_PASSWORD" PG_MONITOR_PASSWORD="$PG_MONITOR_PASSWORD" \
    BOOTSTRAP_ADMIN_EMAIL=founder@example.com BOOTSTRAP_ADMIN_PASSWORD="founder-$(rnd)" \
    DATABASE_OWNER_URL="postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$DB_PORT/$POSTGRES_DB" \
    DATABASE_URL="postgresql+asyncpg://$APP_DB_USER:$APP_DB_PASSWORD@127.0.0.1:$DB_PORT/$POSTGRES_DB" \
    uv run python -m backend.cli.init_db >/dev/null 2>&1); then
  pass "migrations applied (head incl. 0022)"
else
  fail "migrations failed"; exit 1
fi

if python3 "$(dirname "$0")/datastores_check.py" --otlp "$OTLP" --grafana "$GRAFANA" \
    --project "$COMPOSE_PROJECT" --repo "$REPO_ROOT" --alloy-ui "http://127.0.0.1:$ALLOY_UI_PORT"; then
  :
else
  FAILURES=$((FAILURES + 1))
fi
if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
