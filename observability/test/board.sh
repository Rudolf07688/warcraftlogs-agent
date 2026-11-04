#!/usr/bin/env bash
# sc-407: team board entries reach Loki through the redaction chain with their traceparent,
# with only the allowlisted index labels; a seeded secret arrives masked; after Loki loses
# its data the board backfills from the file; entries posted while Loki is down arrive.
# QA fix round: entries outside Loki's accept window (before the schema start, far in the
# future) never reach the Loki exporter and don't hold back current ones; only board files
# are tailed and only board entries forwarded; an OTLP sender claiming team-board stays in
# the content stream.
#   observability/test/board.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"

# A real board, written by board.py in a throwaway git repository, as in a sprint.
REPO_DIR="$(mktemp -d)"
git init -q "$REPO_DIR"
export TEAM_BOARD_DIR="$REPO_DIR/.git/team-board"
cleanup() { stack_down; rm -rf "$REPO_DIR"; }
trap cleanup EXIT

RUN="t$(hex 4)"
TP="00-$(hex 16)-$(hex 8)-01"
post() { (cd "$REPO_DIR" && env -u TRACEPARENT ${2:+TRACEPARENT="$2"} \
  python3 "$REPO_ROOT/.claude/team/board.py" post "$1" "$3" --as "$4" >/dev/null); }
(cd "$REPO_DIR" && python3 "$REPO_ROOT/.claude/team/board.py" init "sprint-$RUN" >/dev/null)
post decision "" "$RUN plain shell entry" maren
post handoff "$TP" "$RUN handoff password=hunter2-$RUN token ghp_$(hex 16)" ansel

# Seeded next to it: an older sprint's board with an entry from before Loki's schema start and
# one far in the future; a selftest board holding lines that are not board entries; and a
# JSONL file that is not a board at all.
entry() { printf '{"id": %s, "ts": "%s", "author": "maren", "kind": "notice", "text": "%s"}\n' "$@"; }
days_ago() { date -u -d "@$(( $(date +%s) - $1 * 86400 ))" +%Y-%m-%dT%H:%M:%SZ; }
BD="$TEAM_BOARD_DIR"
{ entry 1 "2025-12-30T10:00:00Z" "$RUN before the schema start"
  entry 2 "2030-01-01T00:00:00Z" "$RUN far future"; } > "$BD/sprint-old$RUN.jsonl"
{ echo "{\"ts\": \"$(days_ago 0)\", \"author\": \"x\", \"note\": \"$RUN no text or kind\"}"
  echo "$RUN not json at all"; } > "$BD/selftest-$RUN.jsonl"
entry 1 "$(days_ago 0)" "$RUN not a board file" > "$BD/notes-$RUN.jsonl"

stack_up

SEL="{service_name=\"team-board\"} |= \"$RUN\""
poll 120 loki_has "$SEL" || fail "board entries not in Loki"

loki_lines "$SEL" > "$REPO_DIR/q.json"
if python3 - "$REPO_DIR/q.json" "$RUN" "$TP" <<'PY'
import json, sys
res = json.load(open(sys.argv[1]))["data"]["result"]
run, tp = sys.argv[2], sys.argv[3]
lines = {v[1]: s["stream"] for s in res for v in s["values"]}
ok = True
def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg); ok &= bool(cond)
plain = next((m for l, m in lines.items() if "plain shell" in l), None)
hand = next(((l, m) for l, m in lines.items() if "handoff" in l), (None, None))
check(plain is not None and "trace_id" not in plain, "entry without TRACEPARENT is in Loki, without a trace id")
check(hand[1] and hand[1].get("trace_id") == tp.split("-")[1] and hand[1].get("span_id") == tp.split("-")[2],
      "handoff carries the posting traceparent as trace_id and span_id")
check(hand[0] and "hunter2" not in hand[0] and "password=<redacted>" in hand[0] and "ghp_<redacted>" in hand[0],
      "seeded secrets in the entry text arrive masked")
check(hand[1] and hand[1].get("author") == "ansel" and hand[1].get("kind") == "handoff"
      and hand[1].get("board") == f"sprint-{run}", "author, kind and board are kept on the record")
check(all(m.get("content") != "true" for m in lines.values()), "board entries are not in the content stream")
sys.exit(0 if ok else 1)
PY
then :; else FAILURES=$((FAILURES + 1)); fi

labels=$(gq loki loki/api/v1/labels --data-urlencode "start=$(( $(date +%s) - 3600 ))000000000")
if python3 -c 'import json,sys; extra=set(json.loads(sys.argv[1])["data"])-{"service_namespace","service_name","deployment_environment_name","app_layer","level","content"}; print(sorted(extra)); sys.exit(1 if extra else 0)' "$labels"; then
  pass "index labels are within the spec §9.2 allowlist"
else
  fail "index labels outside the allowlist: $labels"
fi

# The current entries above landed although the outside-window ones were read with them.
sleep 20  # every seeded file has been read and exported by now
board_texts="$(loki_lines "{service_name=\"team-board\"} |= \"$RUN\"")"
for t in "before the schema start" "far future" "no text or kind" "not json at all" "not a board file"; do
  grep -q "$RUN $t" <<<"$board_texts" && fail "'$t' reached Loki" || pass "'$t' is not in Loki"
done
# Alloy dropped those two before the export queue (Loki would refuse them: before the schema
# start a retryable 503 that held the queue, live-check:055:board). Loki itself refuses an
# entry more than an hour behind the newest in its stream with a 400, dropped by the exporter
# (not a stuck queue), so an in-window but older entry is not asserted here.
filtered="$(curl -sf "http://127.0.0.1:${ALLOY_UI_PORT}/metrics" | python3 -c '
import sys
print(int(sum(float(l.rsplit(" ", 1)[1]) for l in sys.stdin
              if l.startswith("otelcol_processor_filter_logs_filtered_total") and "filter.log_window" in l)))')"
(( filtered >= 2 )) && pass "the log window dropped the entries outside Loki's window ($filtered)" \
  || fail "the log window dropped $filtered records, expected the 2 seeded ones"

# Path, not payload: an OTLP sender claiming the board (name, layer, even the marker) is content.
spoof='{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"team-board"}},{"key":"app.layer","value":{"stringValue":"build"}}]},"scopeLogs":[{"logRecords":[{"timeUnixNano":"'"$(now_ns)"'","body":{"stringValue":"'"$RUN spoofed board"'"},"attributes":[{"key":"alloy.board","value":{"stringValue":"true"}}]}]}]}]}'
post_otlp logs "$spoof"
poll 60 loki_has "{service_name=\"team-board\", content=\"true\"} |= \"$RUN spoofed board\"" \
  && pass "an OTLP record claiming team-board lands in the content stream" \
  || fail "the spoofed team-board record is not in the content stream"
loki_has "{service_name=\"team-board\", content!=\"true\"} |= \"$RUN spoofed board\"" \
  && fail "the spoofed team-board record is in the board's stream" || pass "the spoofed record is not in the board's stream"

# The board's own stream (the spoofed record above is in the content stream, never backfilled).
count() { loki_lines "{service_name=\"team-board\", content!=\"true\"} |= \"$RUN\"" | python3 -c 'import json,sys; print(sum(len(s["values"]) for s in json.load(sys.stdin)["data"]["result"]))' 2>/dev/null || echo 0; }

# Loki down: an entry posted meanwhile arrives once Loki is back (Alloy's queue).
dc stop loki >/dev/null
post notice "" "$RUN posted while loki was down" ansel
sleep 10
dc start loki >/dev/null
poll 180 loki_has "{service_name=\"team-board\"} |= \"$RUN posted while loki was down\"" \
  && pass "an entry posted while Loki was down arrives after it restarts" \
  || fail "entry posted during the Loki outage never arrived"

# Loki loses its data: the board backfills from the file.
before=$(count)
dc rm -sf loki >/dev/null
docker volume rm "${COMPOSE_PROJECT}_loki-data" >/dev/null
dc up -d --wait loki >/dev/null
loki_up() { gq loki loki/api/v1/labels >/dev/null 2>&1; }
poll 120 loki_up || true
[[ "$(count)" == 0 ]] && pass "Loki starts empty after losing its volume" || fail "Loki still has board entries"
COMPOSE_PROJECT="$COMPOSE_PROJECT" "$REPO_ROOT/observability/board-backfill.sh" >/dev/null
wait_ready
backfilled() { [[ "$(count)" == "$before" ]]; }
poll 180 backfilled && pass "backfill restores all $before board entries" \
  || fail "backfill: expected $before entries, got $(count)"
# A second backfill must not duplicate entries Loki already holds.
"$REPO_ROOT/observability/board-backfill.sh" >/dev/null
sleep 30
[[ "$(count)" == "$before" ]] && pass "a second backfill adds no duplicates" || fail "duplicates after a second backfill: $(count)"

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
