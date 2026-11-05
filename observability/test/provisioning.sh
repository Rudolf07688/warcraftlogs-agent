#!/usr/bin/env bash
# sc-399: the Mimir, Loki and Tempo datasources load from the repository's provisioning
# files on first start, are healthy, and carry the correlation settings: trace -> logs,
# log line (trace_id) -> trace, exemplar -> trace. The clicks themselves are a live check.
# Also Grafana's access settings (anonymous Viewer, admin password, no plugin preinstall).
# Feature 059: the Pyroscope datasource, trace -> profile and the service map; the D6 service
# graph query returns an edge; a CPU-bound span run through the real bootstrap carries a
# profile id and Pyroscope returns that span's flame graph; the board window (an entry older
# than 6 days is dropped, a fresh one in the same file lands).
#   observability/test/provisioning.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
trap stack_down EXIT
export PYROSCOPE_PORT="${PYROSCOPE_PORT:-24040}"
PYROSCOPE="http://127.0.0.1:${PYROSCOPE_PORT}"

# The board window (board scope:059:board-window), seeded before Alloy starts tailing.
BOARD_RUN="win$(hex 4)"
days_ago() { date -u -d "@$(( $(date +%s) - $1 * 86400 ))" +%Y-%m-%dT%H:%M:%SZ; }
{ printf '{"id": 1, "ts": "%s", "author": "maren", "kind": "notice", "text": "%s old"}\n' "$(days_ago 8)" "$BOARD_RUN"
  printf '{"id": 2, "ts": "%s", "author": "maren", "kind": "notice", "text": "%s fresh"}\n' "$(days_ago 0)" "$BOARD_RUN"
} > "$TEAM_BOARD_DIR/sprint-$BOARD_RUN.jsonl"

stack_up
dc up -d --wait pyroscope >/dev/null
poll 120 curl -sf -o /dev/null "$PYROSCOPE/ready" || fail "pyroscope not ready"

for uid in mimir loki tempo pyroscope; do
  ds="$(curl -sf "$GRAFANA/api/datasources/uid/$uid" || true)"
  [[ -n "$ds" ]] && python3 -c 'import sys,json; sys.exit(0 if json.load(sys.stdin)["readOnly"] else 1)' <<<"$ds" \
    && pass "$uid datasource provisioned from file (read-only)" || fail "$uid datasource missing or editable"
  curl -sf "$GRAFANA/api/datasources/uid/$uid/health" | grep -q '"status":"OK"' \
    && pass "$uid datasource healthy" || fail "$uid health check"
done

# check UID PYTHON-EXPRESSION DESCRIPTION: evaluate the expression on the datasource's jsonData (j).
check() {
  curl -sf "$GRAFANA/api/datasources/uid/$1" | python3 -c 'import sys,json
j = json.load(sys.stdin)["jsonData"]
sys.exit(0 if eval(sys.argv[1]) else 1)' "$2" && pass "$3" || fail "$3"
}

check tempo 'j["tracesToLogsV2"]["datasourceUid"] == "loki" and j["tracesToLogsV2"]["filterByTraceID"]' \
  "trace -> logs: Tempo links to Loki, filtered by trace id"
check tempo 'j["tracesToLogsV2"]["customQuery"] and j["tracesToLogsV2"]["query"] == "{${__tags}} | trace_id=\"${__span.traceId}\""' \
  "trace -> logs: query filters on trace_id structured metadata"
check tempo '{t["key"] for t in j["tracesToLogsV2"]["tags"]} == {"service.name", "service.namespace"}' \
  "trace -> logs: service.name and service.namespace mapped to Loki labels"
check tempo 'j["tracesToLogsV2"]["spanStartTimeShift"] == "-2s" and j["tracesToLogsV2"]["spanEndTimeShift"] == "2s"' \
  "trace -> logs: span time shift -2 s / +2 s"
check loki 'any(f["datasourceUid"] == "tempo" and f["matcherType"] == "label" and f["matcherRegex"] == "trace_id" and f["url"] == "${__value.raw}" for f in j["derivedFields"])' \
  "log -> trace: Loki derived field on trace_id structured metadata"
check mimir 'any(d["datasourceUid"] == "tempo" and d["name"] == "trace_id" for d in j["exemplarTraceIdDestinations"])' \
  "exemplar -> trace: Mimir exemplars open Tempo"
check tempo 'j["serviceMap"]["datasourceUid"] == "mimir"' "service map: Tempo reads traces_service_graph_* from Mimir"
check tempo 'j["tracesToProfiles"]["datasourceUid"] == "pyroscope" and j["tracesToProfiles"]["profileTypeId"].startswith("process_cpu:cpu:")' \
  "trace -> profile: Tempo opens the span's CPU profile in Pyroscope"

# Both links need trace_id on the stored record, so check one end to end.
trace_id="$(hex 16)"; marker="prov-$(hex 4)"
post_otlp logs '{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"provisioning-test"}}]},"scopeLogs":[{"logRecords":[{"timeUnixNano":"'"$(now_ns)"'","body":{"stringValue":"'"$marker"'"},"traceId":"'"$trace_id"'","spanId":"'"$(hex 8)"'"}]}]}]}'
# The query trace -> logs runs, with the service tag filled in as Grafana does.
poll 120 loki_has "{service_name=\"provisioning-test\"} | trace_id=\"$trace_id\"" \
  && pass "stored log found by its trace_id structured metadata" || fail "trace_id not on the stored log"

# Grafana access (SEC-002): anonymous visitors are Viewers who can Explore and query, but
# can't add datasources; the admin login takes GRAFANA_ADMIN_PASSWORD, never admin/admin.
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
[[ "$(code -X POST "$GRAFANA/api/datasources" -H 'Content-Type: application/json' \
  -d '{"name":"pivot","type":"grafana-postgresql-datasource","access":"proxy","url":"db:5432"}')" == 403 ]] \
  && pass "anonymous visitor can't create a datasource" || fail "anonymous visitor may create a datasource"
curl -sf "$GRAFANA/api/access-control/user/permissions" | python3 -c 'import sys,json
p = json.load(sys.stdin); sys.exit(0 if "datasources:explore" in p and "datasources:query" in p and "datasources:write" not in p else 1)' \
  && pass "anonymous visitor is a Viewer with Explore" || fail "anonymous permissions"
[[ "$(code -u admin:admin "$GRAFANA/api/user")" == 401 ]] && pass "admin/admin refused" || fail "admin/admin accepted"
curl -sf "${GRAFANA_ADMIN[@]}" "$GRAFANA/api/user" | grep -q '"isGrafanaAdmin":true' \
  && pass "admin login with GRAFANA_ADMIN_PASSWORD" || fail "admin login with GRAFANA_ADMIN_PASSWORD"
[[ "$(dc exec -T grafana sh -c 'ls /var/lib/grafana/plugins | wc -l' | tr -d ' ')" == 0 ]] \
  && pass "no plugins preinstalled" || fail "plugins were preinstalled"

# D1/D6/D7 starters and D13: the dashboards load from the repository's JSON, in one folder
# per layer.
dash="$(curl -sf "$GRAFANA/api/search?type=dash-db" || true)"
for want in "build/wcl-cc-overview" "build/wcl-team-improvement" "runtime/wcl-app-api-llm" "runtime/wcl-api-red" "runtime/wcl-rag"; do
  python3 -c 'import sys,json; f,u=sys.argv[1].split("/"); sys.exit(0 if any(d["uid"]==u and d.get("folderTitle")==f for d in json.load(sys.stdin)) else 1)' "$want" <<<"$dash" \
    && pass "dashboard $want provisioned" || fail "dashboard $want missing"
done
check mimir 'j.get("timeInterval") == "60s"' "Mimir minimum interval matches the 60 s backend export"

# --- feature 059 -----------------------------------------------------------------------
# ds_query JSON: Grafana's /api/ds/query, as a panel runs it (anonymous Viewer).
ds_query() { curl -sf -X POST "$GRAFANA/api/ds/query" -H 'Content-Type: application/json' -d "$1"; }

# D6 service graph: a claude-code client span calling an api server span is one edge.
trace_id="$(hex 16)"; client="$(hex 8)"; t0="$(now_ns)"; t1="$(( t0 + 50000000 ))"
span() { # SERVICE SPAN_ID PARENT KIND NAME
  printf '{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"%s"}},{"key":"service.namespace","value":{"stringValue":"wcl-agent"}}]},"scopeSpans":[{"spans":[{"traceId":"%s","spanId":"%s","parentSpanId":"%s","name":"%s","kind":%s,"startTimeUnixNano":"%s","endTimeUnixNano":"%s","attributes":[{"key":"http.route","value":{"stringValue":"/api/health"}}]}]}]}' \
    "$1" "$trace_id" "$2" "$3" "$5" "$4" "$t0" "$t1"
}
# Grafana runs the service map in the browser: it asks Tempo's serviceMap datasource (Mimir)
# for these series by name, one edge per client/server pair. Same queries here.
graph_edges() {
  mimir_has 'sum by (client, server) (rate(traces_service_graph_request_total{client="claude-code", server="api"}[15m]))' \
    && mimir_has 'histogram_quantile(0.5, sum by (le, client, server) (rate(traces_service_graph_request_server_seconds_bucket{client="claude-code", server="api"}[15m])))' \
    && mimir_has 'sum by (client, server) (rate(traces_service_graph_request_server_seconds_sum{client="claude-code", server="api"}[15m]))'
}
# sc-504: the api server span calls Redis, which has no spans of its own (a virtual node). The
# Redis call takes 20 ms of the api's 50.
server="$(hex 8)"; t2="$(( t0 + 20000000 ))"
redis_span() {
  printf '{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"api"}},{"key":"service.namespace","value":{"stringValue":"wcl-agent"}}]},"scopeSpans":[{"spans":[{"traceId":"%s","spanId":"%s","parentSpanId":"%s","name":"GET","kind":3,"startTimeUnixNano":"%s","endTimeUnixNano":"%s","attributes":[{"key":"db.system","value":{"stringValue":"redis"}}]}]}]}' \
    "$trace_id" "$(hex 8)" "$server" "$t0" "$t2"
}
send_pair() { post_otlp traces "{\"resourceSpans\":[$(span claude-code "$client" "" 3 "GET /api/health"),$(span api "$server" "$client" 2 "GET /api/health"),$(redis_span)]}"; }
send_pair
poll 180 graph_edges \
  && pass "D6 service graph: the service map's queries return the claude-code -> api edge with its latency and the node's response time" \
  || fail "service graph queries returned no edge"
# node_avg_ms NODE: a node's average response time as the node graph computes it in the browser
# (Grafana 13 tempo graphTransform.ts): the per-edge rates summed over the edges into the node,
# server seconds / requests, in ms. Prints nothing when the graph would show none.
node_avg_ms() {
  python3 - "$GRAFANA" "$1" <<'PY'
import json, sys, urllib.parse, urllib.request
grafana, node = sys.argv[1:]
def rate_into(metric):
    q = f"sum by (client, server) (rate({metric}[15m]))"
    url = f"{grafana}/api/datasources/proxy/uid/mimir/api/v1/query?" + urllib.parse.urlencode({"query": q})
    rows = json.load(urllib.request.urlopen(url, timeout=15))["data"]["result"]
    rows = [float(r["value"][1]) for r in rows if r["metric"].get("server") == node]
    return sum(rows) if rows else None
total, seconds = rate_into("traces_service_graph_request_total"), rate_into("traces_service_graph_request_server_seconds_sum")
if total and seconds is not None:
    print(f"{seconds / total * 1000:.2f}")
PY
}
# The ruler records the copy once a minute: poll for the asserted values, not for any result.
nodes_have_latency() { python3 -c 'import sys; a, r = map(float, sys.argv[1:]); sys.exit(0 if 45 <= a <= 55 and 15 <= r <= 25 else 1)' \
  "$(node_avg_ms api || true)" "$(node_avg_ms redis || true)" 2>/dev/null; }
poll 180 nodes_have_latency \
  && pass "D6 service graph: api node averages its 50 ms server span, the Redis virtual node its 20 ms client call (sc-504)" \
  || fail "D6 node averages: api '$(node_avg_ms api || true)' ms/r, redis '$(node_avg_ms redis || true)' ms/r (want ~50 and ~20)"

# Span profile: a CPU-bound function under a root span, through the real bootstrap.
read -r prof_trace prof_span < <(cd "$REPO_ROOT" && env -i HOME="$HOME" PATH="$PATH" WCL_LOAD_DOTENV=0 \
  OTEL_EXPORTER_OTLP_ENDPOINT="$OTLP" WCL_ENVIRONMENT=ci WCL_GIT_SHA=prov059 \
  PYROSCOPE_SERVER_ADDRESS="$PYROSCOPE" uv run --quiet python - <<'PY'
import time
from backend.app.telemetry import configure_telemetry
from opentelemetry import trace

configure_telemetry()
tracer = trace.get_tracer("provisioning-059")
with tracer.start_as_current_span("profiled slow span", kind=trace.SpanKind.SERVER) as span:
    deadline = time.monotonic() + 4
    n = 0
    while time.monotonic() < deadline:
        n += sum(i * i for i in range(2000))
    ctx = span.get_span_context()
print(format(ctx.trace_id, "032x"), format(ctx.span_id, "016x"))
PY
)
[[ -n "${prof_span:-}" ]] || fail "profiled run printed no span"
span_profile_id() { tempo_trace "$prof_trace" | python3 -c 'import sys,json
t = json.load(sys.stdin)
for b in t.get("trace", t).get("resourceSpans", t.get("batches", [])):
    for s in (x for ss in b.get("scopeSpans", []) for x in ss["spans"]):
        for a in s.get("attributes", []):
            if a["key"] == "pyroscope.profile.id": print(a["value"]["stringValue"])'; }
profile_id_is_span() { [[ "$(span_profile_id)" == "$prof_span" ]]; }
poll 120 profile_id_is_span \
  && pass "the profiled span carries pyroscope.profile.id = its span id" || fail "no pyroscope.profile.id on the profiled span"
# flame SPAN_ID: the span's flame graph has frames below the root (the query Grafana's
# "Profiles for this span" runs).
flame() {
  ds_query '{"from":"now-15m","to":"now","queries":[{"refId":"A","datasource":{"uid":"pyroscope","type":"grafana-pyroscope-datasource"},"queryType":"profile","profileTypeId":"process_cpu:cpu:nanoseconds:cpu:nanoseconds","labelSelector":"{service_name=\"api\"}","spanSelector":["'"$1"'"],"groupBy":[]}]}' \
    | python3 -c 'import sys,json
frames = json.load(sys.stdin)["results"]["A"].get("frames", [])
fg = [f for f in frames if f["schema"].get("meta", {}).get("preferredVisualisationType") == "flamegraph"]
levels = fg[0]["data"]["values"][0] if fg else []
sys.exit(0 if len(levels) > 1 else 1)'
}
poll 120 flame "$prof_span" && pass "Pyroscope returns the flame graph for that span (Profiles for this span)" \
  || fail "no flame graph for the profiled span"
flame "$(hex 8)" && fail "another span id got a flame graph: samples not selected by span" \
  || pass "the flame graph is that span's own (another span id gets none)"

# Board window: the fresh entry lands, the 8-day-old one in the same file is dropped by Alloy.
board_since() { gq loki loki/api/v1/query_range --data-urlencode "query={service_name=\"team-board\"} |= \"$BOARD_RUN $1\"" \
  --data-urlencode "start=$(( $(date +%s) - 9 * 86400 ))000000000" --data-urlencode "limit=10" | has_result; }
poll 120 board_since fresh && pass "board window: today's entry lands" || fail "board window: today's entry missing"
board_since old && fail "board window: an 8-day-old entry reached Loki" || pass "board window: an 8-day-old entry is dropped (accepted, scope:059:board-window)"

# Restarted without GRAFANA_ADMIN_PASSWORD, on the same volume: no admin login at all.
old_password="$GRAFANA_ADMIN_PASSWORD"
GRAFANA_ADMIN_PASSWORD="" dc up -d --wait --no-deps --force-recreate grafana >/dev/null
poll 60 curl -sf -o /dev/null "$GRAFANA/api/health"
[[ "$(code -u admin:admin "$GRAFANA/api/user")" == 401 && "$(code -u "admin:$old_password" "$GRAFANA/api/user")" == 401 ]] \
  && pass "password unset: neither admin/admin nor the old password logs in" || fail "admin login without GRAFANA_ADMIN_PASSWORD"
[[ "$(code "$GRAFANA/api/datasources/proxy/uid/loki/loki/api/v1/labels")" == 200 ]] \
  && pass "password unset: anonymous Viewer still queries" || fail "anonymous query after restart"

echo "provisioning: $FAILURES failure(s)"
[[ $FAILURES == 0 ]] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
