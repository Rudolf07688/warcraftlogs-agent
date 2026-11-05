#!/usr/bin/env bash
# sc-416: D5 (App: Frontend) provisions, and its own panel queries return what the browser sent:
# a component error with its route and boundary, Web Vitals p75 by route, client TTFT, stream
# aborts, sessions and turns. The payloads are shaped like Faro 2.13's (meta.view = the route
# template, as frontend/src/telemetry/faro.ts sets it); the browser itself is a live check.
#   observability/test/frontend.sh        (KEEP=1 leaves the stack up)
# Own stack: COMPOSE_PROJECT / ports as in lib.sh, plus ALLOY_FARO_PORT (default 24347).
source "$(dirname "$0")/lib.sh"
export ALLOY_FARO_PORT="${ALLOY_FARO_PORT:-24347}"
FARO="http://127.0.0.1:${ALLOY_FARO_PORT}/collect"
trap stack_down EXIT

stack_up

RUN="$(hex 6)"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
payload() {
  cat <<JSON
{
  "meta": {
    "sdk": {"name": "@grafana/faro-core", "version": "2.13.0"},
    "app": {"name": "web", "namespace": "wcl-agent", "version": "fe-test", "environment": "dev"},
    "session": {"id": "fe-$RUN"},
    "page": {"url": "http://localhost:5173/app"},
    "view": {"name": "/app/*"}
  },
  "exceptions": [{
    "type": "React ErrorBoundary Error", "value": "synthetic component error $RUN", "timestamp": "$NOW_ISO",
    "stacktrace": {"frames": [{"filename": "http://localhost:5173/src/App.tsx", "function": "Boom", "lineno": 1, "colno": 1}]},
    "context": {"boundary": "messages", "route": "/app/*"}
  }],
  "measurements": [
    {"type": "web-vitals", "values": {"lcp": 2400}, "context": {"rating": "good"}, "timestamp": "$NOW_ISO"},
    {"type": "web-vitals", "values": {"inp": 180}, "context": {"rating": "good"}, "timestamp": "$NOW_ISO"},
    {"type": "web-vitals", "values": {"cls": 0.05}, "context": {"rating": "good"}, "timestamp": "$NOW_ISO"}
  ],
  "events": [
    {"name": "session_start", "timestamp": "$NOW_ISO"},
    {"name": "agent_message_sent", "attributes": {"model": "m1"}, "timestamp": "$NOW_ISO"},
    {"name": "agent_first_token_rendered", "attributes": {"model": "m1", "ttft_ms": "850"}, "timestamp": "$NOW_ISO"},
    {"name": "agent_response_completed", "attributes": {"model": "m1", "duration_ms": "4200"}, "timestamp": "$NOW_ISO"},
    {"name": "agent_message_sent", "attributes": {"model": "m1"}, "timestamp": "$NOW_ISO"},
    {"name": "stream_aborted", "attributes": {"model": "m1", "reason": "connection_lost", "elapsed_ms": "900"}, "timestamp": "$NOW_ISO"}
  ]
}
JSON
}
code="$(payload | curl -s -o /dev/null -w '%{http_code}' -X POST "$FARO" -H 'Content-Type: application/json' \
  -H 'Origin: http://localhost:5173' -H 'x-api-key: wcl-faro-local' --data-binary @-)"
[[ "$code" =~ ^2 ]] && pass "Faro payload accepted ($code)" || fail "Faro payload got $code"
poll 60 loki_has "{service_name=\"web\"} |= \"$RUN\"" && pass "the payload reached Loki" || fail "nothing in Loki"
sleep 5 # the rest of the batch

search="$(curl -sf "$GRAFANA/api/search?type=dash-db" || true)"
python3 -c 'import sys,json; sys.exit(0 if any(d["uid"]=="wcl-d5-frontend" and d.get("folderTitle")=="runtime" for d in json.load(sys.stdin)) else 1)' <<<"$search" \
  && pass "D5 provisioned in the runtime folder" || fail "D5 not provisioned"
curl -sf "$GRAFANA/api/dashboards/uid/wcl-d5-frontend" > "/tmp/d5-$COMPOSE_PROJECT.json" || fail "D5 not readable"

# Every D5 query runs as the panel would (range -> 1h, step 60s); the named ones must hold values.
if python3 - "$GRAFANA" "/tmp/d5-$COMPOSE_PROJECT.json" "$RUN" <<'PY'
import json, sys, time, urllib.parse, urllib.request
grafana, path, run = sys.argv[1:]
d = json.load(open(path))["dashboard"]
fails = 0
def check(ok, what):
    global fails
    fails += not ok
    print(("PASS  " if ok else "FAIL  ") + what)
def loki(expr, instant):
    now = int(time.time())
    if instant:
        q = {"query": expr.replace("$__range", "1h"), "time": str(now)}
        url = "loki/api/v1/query"
    else:
        q = {"query": expr.replace("$__auto", "1m"), "start": str(now - 3600), "end": str(now), "step": "60"}
        url = "loki/api/v1/query_range"
    body = urllib.request.urlopen(f"{grafana}/api/datasources/proxy/uid/loki/{url}?{urllib.parse.urlencode(q)}", timeout=20).read()
    return json.loads(body)["data"]["result"]
results = {}
for p in d["panels"]:
    for t in p.get("targets", []):
        try:
            res = loki(t["expr"], t.get("queryType") == "instant")
            results[(p["title"], t["refId"])] = res
            check(True, f"'{p['title']}' {t['refId']} runs")
        except Exception as e:
            check(False, f"'{p['title']}' {t['refId']} runs ({e})")
def value(r):  # instant vector sample, or the last range sample
    return float(r["value"][1]) if "value" in r else float(r["values"][-1][1])
top = results.get(("Top errors", "A"), [])
check(any(r["metric"].get("view_name") == "/app/*" and r["metric"].get("context_boundary") == "messages"
          and run in r["metric"].get("value", "") and value(r) == 1 for r in top),
      "Top errors: the synthetic component error with route /app/* and boundary messages, count 1")
vitals = {ref: results.get(("Web Vitals p75 by route", ref), []) for ref in "ABC"}
for ref, name, want in (("A", "LCP", 2400), ("B", "INP", 180), ("C", "CLS", 0.05)):
    check(any(r["metric"].get("view_name") == "/app/*" and abs(value(r) - want) < 1e-6 for r in vitals[ref]),
          f"Web Vitals: {name} p75 for /app/* is {want}")
stats = {p["title"]: results.get((p["title"], "A"), []) for p in d["panels"] if p["type"] == "stat"}
for title, want in (("Sessions", 1), ("Turns sent", 2), ("JS errors", 1), ("Client TTFT p95", 850),
                    ("Stream aborts", 1), ("Completed turns", 1)):
    got = [value(r) for r in stats.get(title, [])]
    check(got == [want], f"stat '{title}' is {want} (got {got})")
aborts = results.get(("Stream aborts per interval", "A"), [])
check(sum(value(r) for r in aborts if r["metric"].get("event_data_reason") == "connection_lost") == 1,
      "Stream aborts per interval: one connection_lost abort")
ttft = results.get(("Client TTFT", "B"), [])
check(any(r["metric"].get("event_data_model") == "m1" and any(float(v) == 850 for _, v in r["values"]) for r in ttft),
      "Client TTFT: p95 850 ms for model m1")
errs = results.get(("JS errors / min by route", "A"), [])
check(any(r["metric"].get("view_name") == "/app/*" and any(float(v) > 0 for _, v in r["values"]) for r in errs),
      "JS errors / min: a non-zero rate on /app/*")
sys.exit(1 if fails else 0)
PY
then :; else FAILURES=$((FAILURES + 1)); fi
rm -f "/tmp/d5-$COMPOSE_PROJECT.json"

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
