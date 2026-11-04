# Shared helpers for the observability test scripts (feature 053). Source it, don't run it.
#
# The scripts run their own compose project (default wcl-obs-test) on non-default loopback
# ports, so they never touch the app stack or the owner's telemetry, and they remove it
# with its volumes when they finish (KEEP=1 keeps it for a look around).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export COMPOSE_PROJECT="${COMPOSE_PROJECT:-wcl-obs-test}"
export ALLOY_OTLP_GRPC_PORT="${ALLOY_OTLP_GRPC_PORT:-24317}"
export ALLOY_OTLP_HTTP_PORT="${ALLOY_OTLP_HTTP_PORT:-24318}"
export ALLOY_UI_PORT="${ALLOY_UI_PORT:-22345}"
export GRAFANA_PORT="${GRAFANA_PORT:-23000}"
OTLP="http://127.0.0.1:${ALLOY_OTLP_HTTP_PORT}"
GRAFANA="http://127.0.0.1:${GRAFANA_PORT}"
BACKENDS=(loki tempo mimir)
# The team board dir Alloy tails (feature 055): a fresh empty one per run, never the real
# board (board.sh writes test entries into it).
export TEAM_BOARD_DIR="${TEAM_BOARD_DIR:-$(mktemp -d)}"
hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }
# A fresh admin password per run (Grafana's admin login; anonymous visitors are Viewers).
export GRAFANA_ADMIN_PASSWORD="test-$(hex 12)"
GRAFANA_ADMIN=(-u "admin:$GRAFANA_ADMIN_PASSWORD")
FAILURES=0

# The app services interpolate these; set them empty so compose doesn't warn. The scripts
# never start the app services.
export POSTGRES_USER="${POSTGRES_USER:-}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}" \
  POSTGRES_DB="${POSTGRES_DB:-}" APP_DB_USER="${APP_DB_USER:-}" APP_DB_PASSWORD="${APP_DB_PASSWORD:-}"

# COMPOSE_OVERRIDE: an extra compose file layered on top (queue-drain.sh mounts a Loki config
# with it); unset for every other script.
dc() { (cd "$REPO_ROOT" && docker compose --progress quiet -p "$COMPOSE_PROJECT" \
  ${COMPOSE_OVERRIDE:+-f docker-compose.yml -f "$COMPOSE_OVERRIDE"} --profile observability "$@"); }

# backend_get URL: GET from inside the compose network (Grafana's image has wget).
backend_get() { dc exec -T grafana wget -qO- "$1"; }

stack_up() { dc up -d --wait alloy "${BACKENDS[@]}" grafana >/dev/null; wait_ready; }

stack_down() {
  if [[ "${KEEP:-0}" == 1 ]]; then
    echo "KEEP=1: project $COMPOSE_PROJECT left running (Grafana $GRAFANA)"
  else
    dc down -v >/dev/null
  fi
}

# Alloy accepts OTLP and Grafana answers, with all three datasources reachable.
wait_ready() {
  local i
  for i in $(seq 1 90); do
    if curl -sf -o /dev/null "$OTLP/v1/traces" -X POST -H 'Content-Type: application/json' -d '{}' \
      && curl -sf -o /dev/null "$GRAFANA/api/datasources/proxy/uid/loki/loki/api/v1/labels" \
      && curl -sf -o /dev/null "$GRAFANA/api/datasources/proxy/uid/tempo/api/echo" \
      && curl -sf -o /dev/null "$GRAFANA/api/datasources/proxy/uid/mimir/api/v1/labels"; then
      return 0
    fi
    sleep 2
  done
  echo "stack not ready after 180 s" >&2
  return 1
}

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILURES=$((FAILURES + 1)); }

now_ns() { echo "$(date +%s)000000000"; }

# post_otlp SIGNAL JSON: send one OTLP/HTTP JSON request to Alloy.
post_otlp() {
  curl -sf -o /dev/null -X POST "$OTLP/v1/$1" -H 'Content-Type: application/json' -d "$2"
}

# Grafana datasource proxy GET, so the backends need no host ports.
gq() { curl -sf -G "$GRAFANA/api/datasources/proxy/uid/$1/$2" "${@:3}"; }

# poll SECONDS CMD...: rerun CMD until it succeeds or the time is up.
poll() {
  local deadline=$(( $(date +%s) + $1 )); shift
  until "$@"; do
    (( $(date +%s) >= deadline )) && return 1
    sleep 3
  done
}

# loki_lines LOGQL: the raw query_range result (last hour) as JSON.
loki_lines() {
  gq loki loki/api/v1/query_range --data-urlencode "query=$1" \
    --data-urlencode "start=$(( $(date +%s) - 3600 ))000000000" --data-urlencode "limit=100"
}

# has_result: exit 0 iff stdin is a Loki/Prometheus JSON answer with a non-empty result
# (a backend still starting answers with plain text: that counts as "not yet").
has_result() { python3 -c 'import sys,json
try: sys.exit(0 if json.load(sys.stdin)["data"]["result"] else 1)
except Exception: sys.exit(1)'; }

loki_has() { loki_lines "$1" | has_result; }

tempo_trace() { gq tempo "api/v2/traces/$1" -H 'Accept: application/json'; }

tempo_has() { tempo_trace "$1" >/dev/null; }

mimir_query() { gq mimir api/v1/query --data-urlencode "query=$1"; }

mimir_has() { mimir_query "$1" | has_result; }
