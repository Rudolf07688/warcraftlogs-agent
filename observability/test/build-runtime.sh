#!/usr/bin/env bash
# sc-422: a synthetic regression commit shows up on D12 (Build vs Runtime) against its authoring
# seat. Two api versions run one after the other (A fast and clean, B slow, failing and costlier
# per request) as real OTLP spans and metrics through Alloy; a synthetic team board names A in
# Nils's hand-off and B in Tomas's hand-off plus Maren's merge; commits.py pushes the board facts.
# Then D12's own table, timeseries and annotation queries must show B against tomas (dev-2)
# with positive deltas and its build cost, and A against nils (dev-3).
#   observability/test/build-runtime.sh        (KEEP=1 leaves the stack up; PHASE_S=240 per version)
source "$(dirname "$0")/lib.sh"
export ALLOY_FARO_PORT="${ALLOY_FARO_PORT:-24347}" # compose publishes it; never the app stack's
trap 'stack_down; rm -rf "$meta"' EXIT
meta="$(mktemp -d)"

stack_up

A="$(hex 4 | cut -c1-7)"; B="$(hex 4 | cut -c1-7)"
mkdir -p "$meta/team" "$meta/sprints/synthetic" "$meta/boards"
for s in "dev-2 Tomas" "dev-3 Nils" "po Maren"; do
  set -- $s
  printf -- '# %s\n\n- **name:** %s\n- **seat:** %s\n' "$2" "$2" "$1" > "$meta/team/$1.md"
done
NOW="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
cat > "$meta/sprints/synthetic/board.jsonl" <<JSON
{"id": 1, "ts": "$NOW", "author": "nils", "kind": "handoff", "text": "998 done", "key": "status:998", "refs": ["$A"]}
{"id": 2, "ts": "$NOW", "author": "tomas", "kind": "handoff", "text": "999 done", "key": "status:999", "refs": ["${B}0"]}
{"id": 3, "ts": "$NOW", "author": "maren", "kind": "merge", "text": "999 merged", "key": "status:999", "refs": ["$B"]}
JSON
# 999's usage: (out 100000 * 5 + cacheRd 10000000 * 0.1 + cacheWr 400000 * 1.25) / 1e6 = 2 M units, $8.
cat > "$meta/sprints/synthetic/usage.txt" <<'TXT'
agent                                     calls      out     cacheRd    cacheWr  sends
999 synthetic regression (Tomas)             10   100000    10000000     400000      0
TOTAL {}
TXT
python3 "$REPO_ROOT/observability/build-runtime/commits.py" --meta "$meta" --board-dir "$meta/boards" --endpoint "$OTLP" \
  | tee "$meta/commits.out"
grep -q "$B  tomas (dev-2)      999 .* 8.00$" "$meta/commits.out" && pass "commits.py: B attributed to tomas (dev-2) at \$8.00" \
  || fail "commits.py did not attribute B to tomas (dev-2) with \$8.00"

if python3 - "$OTLP" "$GRAFANA" "$A" "$B" "${PHASE_S:-240}" "$REPO_ROOT/observability/grafana/dashboards/cross/build-runtime.json" <<'PY'
import json, random, secrets, sys, time, urllib.parse, urllib.request
otlp, grafana, A, B, phase_s, dash = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6]
fails = 0
def check(ok, what):
    global fails
    fails += not ok
    print(("PASS  " if ok else "FAIL  ") + what)
def post(signal, body):
    req = urllib.request.Request(f"{otlp}/v1/{signal}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()
def mimir(path, **params):
    try:
        return json.load(urllib.request.urlopen(f"{grafana}/api/datasources/proxy/uid/mimir/{path}?{urllib.parse.urlencode(params)}", timeout=20))
    except Exception:
        return {}
def query(q):
    return (mimir("api/v1/query", query=q).get("data") or {}).get("result") or []
def a(d): return [{"key": k, "value": {"stringValue": v}} for k, v in d.items()]
def res(version):
    return {"attributes": a({"service.name": "api", "service.namespace": "wcl-agent", "service.version": version,
                             "vcs.ref.head.revision": version, "app.layer": "runtime", "deployment.environment.name": "dev"})}

deadline = time.time() + 150
while time.time() < deadline:
    files = {g["file"].rsplit("/", 1)[-1] for g in (mimir("api/v1/rules").get("data") or {}).get("groups") or []}
    if "cross.yaml" in files:
        break
    time.sleep(5)
check("cross.yaml" in files, "the ruler loaded cross.yaml")

start = time.time_ns()
tokens = 0.0
turns = 0
def tick(version, slow):
    """One 10-second batch: 6 server spans, the version's target_info, a cumulative token count."""
    global tokens, turns
    now = time.time_ns()
    spans = []
    for i in range(6):
        dur = int((1.5 if slow else 0.05) * 1e9 * random.uniform(0.9, 1.1))
        # One error in A's first batch creates the error series up front: a counter's first
        # sample is not counted by rate(), so B's errors would otherwise start late.
        error = (slow and i < 2) or (not slow and turns == 0 and i == 0)
        spans.append({"traceId": secrets.token_hex(16), "spanId": secrets.token_hex(8), "name": "GET /api/conversations",
                      "kind": 2, "startTimeUnixNano": str(now - dur), "endTimeUnixNano": str(now),
                      "attributes": a({"http.route": "/api/conversations", "http.request.method": "GET"}),
                      "status": {"code": 2 if error else 1}})
    post("traces", {"resourceSpans": [{"resource": res(version), "scopeSpans": [{"scope": {"name": "d12-test"}, "spans": spans}]}]})
    turns += 1
    tokens += 30000.0 if slow else 3000.0  # B spends ten times the tokens per request
    hist = {"name": "gen_ai.client.token.usage", "unit": "{token}", "exponentialHistogram": {"aggregationTemporality": 2, "dataPoints": [
        {"startTimeUnixNano": str(start), "timeUnixNano": str(now), "count": str(turns), "sum": tokens, "scale": 0, "zeroCount": "0",
         "positive": {"offset": 9, "bucketCounts": [str(turns)]},
         "attributes": a({"gen_ai.request.model": "gemini-3.6-flash", "gen_ai.token.type": "input", "gen_ai.agent.name": "wcl_agent"})}]}}
    up = {"name": "d12_test_up", "gauge": {"dataPoints": [{"timeUnixNano": str(now), "asDouble": 1}]}}
    post("metrics", {"resourceMetrics": [{"resource": res(version), "scopeMetrics": [{"scope": {"name": "d12-test"}, "metrics": [hist, up]}]}]})

t0 = time.time()
# A runs a minute longer: the stack's first spanmetrics flush and rate windows eat into it.
for version, slow, secs in ((A, False, phase_s + 60), (B, True, phase_s)):
    end = time.time() + secs
    while time.time() < end:
        tick(version, slow)
        time.sleep(10)
    print(f"INFO  version {version} ran {secs} s ({'slow, failing' if slow else 'fast, clean'})")
time.sleep(150)  # spanmetrics flush plus two ruler evaluations
rng = f"{int(time.time() - t0) + 60}s"

health = [(r["name"], r.get("health"), r.get("lastError")) for g in (mimir("api/v1/rules").get("data") or {}).get("groups") or []
          if g["file"].endswith("cross.yaml") for r in g["rules"]]
bad = [h for h in health if h[1] != "ok"]
check(len(health) == 9 and not bad, f"all 9 cross rules evaluate ({bad[:2]})")

d = json.load(open(dash))
table = next(p for p in d["panels"] if p["type"] == "table")
rows = {}
for t in table["targets"]:
    for r in query(t["expr"].replace("$__range", rng)):
        m = r["metric"]
        rows.setdefault(m["commit"], {"seat": m.get("seat")})[t["refId"]] = float(r["value"][1])
print("INFO  table rows:", json.dumps(rows))
b, a_ = rows.get(B, {}), rows.get(A, {})
check(b.get("seat") == "tomas (dev-2)", "table: the regression commit B is against tomas (dev-2)")
check(a_.get("seat") == "nils (dev-3)", "table: commit A is against nils (dev-3)")
check(b.get("A", 0) > 0.2 and a_.get("A", 0) < 0, f"table: Δ p95 positive for B ({b.get('A')}), negative for A ({a_.get('A')})")
check(b.get("B", 0) > 0 and a_.get("B", 1) < 0, f"table: Δ error ratio positive for B ({b.get('B')}), negative for A ({a_.get('B')})")
check(b.get("C", 0) > 0 and a_.get("C", 1) < 0, f"table: Δ LLM cost / request positive for B ({b.get('C')}), negative for A ({a_.get('C')})")
check(b.get("D") == 8.0 and "D" not in a_, f"table: build cost $8.00 for B, none for A (B {b.get('D')}, A {a_.get('D')})")

ann = d["annotations"]["list"][0]["expr"]
now = int(time.time())
r = mimir("api/v1/query_range", query=ann, start=str(now - int(rng[:-1])), end=str(now), step="60")
seen = {s["metric"].get("commit"): s["metric"].get("seat") for s in (r.get("data") or {}).get("result") or []}
check(seen.get(A) == "nils (dev-3)" and seen.get(B) == "tomas (dev-2)", f"annotations: both commits with their seats ({seen})")
for p in d["panels"]:
    for t in p.get("targets", []):
        if p["type"] == "timeseries":
            got = {s["metric"].get("commit") for s in (mimir("api/v1/query_range", query=t["expr"], start=str(now - 900), end=str(now), step="60").get("data") or {}).get("result") or []}
            check({A, B} <= got, f"'{p['title']}' shows both commits")
sys.exit(1 if fails else 0)
PY
then :; else FAILURES=$((FAILURES + 1)); fi

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
