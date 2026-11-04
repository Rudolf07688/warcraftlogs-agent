#!/usr/bin/env bash
# QA fix round (board live-check:055:board): a Loki queue stuck on a refusal drains once the
# fix is deployed onto the same volumes, and moving Loki's schema start keeps its data.
#   1. The old setup: Alloy without the log window, Loki's schema starting yesterday. A board
#      entry from two days ago gets Loki's retryable 503 ("no schema config found"), and a
#      current entry read in the same batch is stuck with it in the disk queue.
#   2. The repository's Alloy and Loki config on the same volumes: the queued batch is
#      accepted, both entries land, and a log stored before the switch is still there.
#   observability/test/queue-drain.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
work="$(mktemp -d)"
REPO_DIR="$work/repo"
git init -q "$REPO_DIR"
export TEAM_BOARD_DIR="$REPO_DIR/.git/team-board"
cleanup() { stack_down; rm -rf "$work"; }
trap cleanup EXIT

# Phase 1 config: copies, so the checkout is never written.
export ALLOY_CONFIG_DIR="$work/alloy"
mkdir "$ALLOY_CONFIG_DIR"
cp -p "$REPO_ROOT"/observability/alloy/* "$ALLOY_CONFIG_DIR/"
python3 - "$ALLOY_CONFIG_DIR/config.alloy" <<'PY'
import sys
path = sys.argv[1]
text = open(path).read()
old = "logs    = [otelcol.processor.filter.log_window.input]"
assert text.count(old) == 1, "log window wiring not found"
open(path, "w").write(text.replace(old, "logs    = [otelcol.processor.transform.classify.input]"))
PY
yesterday="$(date -u -d '-1 day' +%Y-%m-%d)"
sed "s/from: \"[0-9-]*\"/from: \"$yesterday\"/" "$REPO_ROOT/observability/loki/loki.yaml" > "$work/loki.yaml"
grep -q "from: \"$yesterday\"" "$work/loki.yaml" || { echo "schema date not set"; exit 1; }
chmod -R a+rX "$work"
export COMPOSE_OVERRIDE="$work/override.yml"
cat > "$COMPOSE_OVERRIDE" <<EOF
services:
  loki:
    volumes:
      - $work/loki.yaml:/etc/loki/loki.yaml:ro
EOF

RUN="q$(hex 4)"
(cd "$REPO_DIR" && python3 "$REPO_ROOT/.claude/team/board.py" init "sprint-$RUN" >/dev/null)
ts() { date -u -d "$1" +%Y-%m-%dT%H:%M:%SZ; }
{ printf '{"id": 1, "ts": "%s", "author": "maren", "kind": "notice", "text": "%s"}\n' "$(ts '-2 days')" "$RUN two days old"
  printf '{"id": 2, "ts": "%s", "author": "maren", "kind": "notice", "text": "%s"}\n' "$(ts now)" "$RUN current"
} > "$TEAM_BOARD_DIR/sprint-$RUN.jsonl"

stack_up
echo "phase 1: old setup (no log window, Loki schema from $yesterday)"
sleep 60
loki_has "{service_name=\"team-board\"} |= \"$RUN current\"" \
  && fail "phase 1 did not reproduce the stuck queue (the current entry landed)" \
  || pass "phase 1: the current entry is stuck behind the pre-schema one"
post_otlp logs '{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"drain-test"}}]},"scopeLogs":[{"logRecords":[{"timeUnixNano":"'"$(now_ns)"'","body":{"stringValue":"'"$RUN stored before the switch"'"}}]}]}]}'
before_switch() { loki_has "{service_name=\"drain-test\"} |= \"$RUN stored before the switch\""; }
poll 90 before_switch && pass "phase 1: a log in its own batch lands" || fail "phase 1: the separate log never landed"

echo "phase 2: the repository's Alloy and Loki config, same volumes"
unset COMPOSE_OVERRIDE
export ALLOY_CONFIG_DIR="$REPO_ROOT/observability/alloy"
dc up -d --wait alloy loki >/dev/null
wait_ready
current() { loki_has "{service_name=\"team-board\"} |= \"$RUN current\""; }
two_days() {
  gq loki loki/api/v1/query_range --data-urlencode "query={service_name=\"team-board\"} |= \"$RUN two days old\"" \
    --data-urlencode "start=$(( $(date +%s) - 3 * 86400 ))000000000" --data-urlencode "limit=10" | has_result
}
poll 240 current && pass "phase 2: the stuck current entry lands (the queue drained)" \
  || fail "phase 2: the current entry is still stuck"
poll 60 two_days && pass "phase 2: the two-day-old entry lands too (now inside the schema)" \
  || fail "phase 2: the two-day-old entry never landed"
before_switch && pass "phase 2: the log stored before the schema move is still in Loki" \
  || fail "phase 2: the schema move lost stored data"

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
