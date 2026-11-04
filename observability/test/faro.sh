#!/usr/bin/env bash
# sc-414: the Faro receiver takes browser telemetry from the app origin with the key, refuses
# everything else, rate limits, and what it takes arrives in Loki after the redaction chain
# (a seeded secret masked) and as a trace in Tempo.
#   observability/test/faro.sh        (KEEP=1 leaves the stack up)
# Own stack: COMPOSE_PROJECT / ports as in lib.sh, plus ALLOY_FARO_PORT (default 24347).
source "$(dirname "$0")/lib.sh"
export ALLOY_FARO_PORT="${ALLOY_FARO_PORT:-24347}"
FARO="http://127.0.0.1:${ALLOY_FARO_PORT}/collect"
KEY="wcl-faro-local"           # the receiver's api_key (a public value: it ships in the bundle)
ORIGIN="http://localhost:5173" # the app origin the receiver allows
trap stack_down EXIT

stack_up

RUN="$(hex 6)"
SESSION="faro-$RUN"
SECRET="faro-secret-$RUN"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
TRACE_ID="$(hex 16)"; SPAN_ID="$(hex 8)"
START_NS="$(now_ns)"; END_NS="$(( $(date +%s) * 1000000000 + 50000000 ))"

payload() {
  cat <<JSON
{
  "meta": {
    "sdk": {"name": "@grafana/faro-core", "version": "2.13.0"},
    "app": {"name": "web", "namespace": "wcl-agent", "version": "faro-test", "environment": "dev"},
    "session": {"id": "$SESSION"},
    "page": {"url": "http://localhost:5173/app"}
  },
  "logs": [{
    "message": "faro test $RUN Authorization: Bearer $SECRET and password=$SECRET",
    "level": "error", "context": {"run": "$RUN"}, "timestamp": "$NOW_ISO"
  }],
  "measurements": [{
    "type": "web-vitals", "values": {"lcp": 1234.5, "cls": 0.01},
    "context": {"run": "$RUN"}, "timestamp": "$NOW_ISO"
  }],
  "traces": {"resourceSpans": [{
    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "web"}}]},
    "scopeSpans": [{"scope": {"name": "faro-test"}, "spans": [{
      "traceId": "$TRACE_ID", "spanId": "$SPAN_ID", "name": "faro-test-$RUN", "kind": 1,
      "startTimeUnixNano": "$START_NS", "endTimeUnixNano": "$END_NS",
      "attributes": [{"key": "session.id", "value": {"stringValue": "$SESSION"}}]
    }]}]
  }]}
}
JSON
}

# post ORIGIN KEY [PAYLOAD-FUNCTION]: the HTTP status of one POST to the receiver.
post() {
  "${3:-payload}" | curl -s -o /dev/null -w '%{http_code}' -X POST "$FARO" \
    -H 'Content-Type: application/json' -H "Origin: $1" -H "x-api-key: $2" --data-binary @-
}

# post_ok FUNCTION: post as the app does, waiting out the rate limit (5/s, burst 10).
post_ok() {
  local code i
  for i in 1 2 3 4 5 6; do
    code="$(post "$ORIGIN" "$KEY" "$1")"
    [[ "$code" != 429 ]] && { echo "$code"; return; }
    sleep 2
  done
  echo "$code"
}

# SEC-002: a payload claiming to be the api, the build layer and prod, with content flags.
SPOOF_TRACE="$(hex 16)"; SPOOF_SPAN="$(hex 8)"
spoof() {
  cat <<JSON
{
  "meta": {"sdk": {"name": "@grafana/faro-core", "version": "2.13.0"},
           "app": {"name": "api", "namespace": "wcl-agent", "version": "x", "environment": "prod"},
           "session": {"id": "$SESSION"}},
  "traces": {"resourceSpans": [{
    "resource": {"attributes": [
      {"key": "service.name", "value": {"stringValue": "claude-code"}},
      {"key": "service.namespace", "value": {"stringValue": "evil-ns"}},
      {"key": "app.layer", "value": {"stringValue": "build"}},
      {"key": "deployment.environment.name", "value": {"stringValue": "prod"}},
      {"key": "content", "value": {"stringValue": "true"}},
      {"key": "app.content", "value": {"stringValue": "true"}}]},
    "scopeSpans": [{"scope": {"name": "spoof"}, "spans": [{
      "traceId": "$SPOOF_TRACE", "spanId": "$SPOOF_SPAN", "name": "spoof-$RUN", "kind": 1,
      "startTimeUnixNano": "$START_NS", "endTimeUnixNano": "$END_NS",
      "attributes": [{"key": "app.content", "value": {"stringValue": "true"}}]
    }]}]
  }]}
}
JSON
}

# SEC-001: an exception whose stack frame names a URL on a listener inside the compose network.
# (The receiver only looks for a source map when the app meta carries a release, and it caches
# per URL, so each probe names its own file and release.)
sourcemap() {
  cat <<JSON
{
  "meta": {"sdk": {"name": "@grafana/faro-core", "version": "2.13.0"},
           "app": {"name": "web", "namespace": "wcl-agent", "version": "faro-test", "release": "faro-test-$PROBE", "environment": "dev"},
           "session": {"id": "$SESSION"}},
  "exceptions": [{
    "type": "Error", "value": "sourcemap probe $RUN", "timestamp": "$NOW_ISO",
    "stacktrace": {"frames": [{"filename": "http://grafana:9999/main$PROBE.js", "function": "f", "lineno": 1, "colno": 10}]}
  }]
}
JSON
}

code="$(post_ok payload)"
[[ "$code" =~ ^2 ]] && pass "app origin with the key is accepted ($code)" || fail "app origin with the key got $code"

code="$(post "$ORIGIN" "wrong-key")"
[[ "$code" == 401 || "$code" == 403 ]] && pass "a wrong key is refused ($code)" || fail "a wrong key got $code"

code="$(post "$ORIGIN" "")"
[[ "$code" == 401 || "$code" == 403 ]] && pass "no key is refused ($code)" || fail "no key got $code"

# CORS: a browser preflights the key header, so the answer to the preflight decides.
preflight() {
  curl -s -D - -o /dev/null -X OPTIONS "$FARO" -H "Origin: $1" \
    -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type,x-api-key'
}
if preflight "$ORIGIN" | grep -qi "^access-control-allow-origin: $ORIGIN"; then
  pass "the preflight from the app origin is allowed"
else
  fail "the preflight from the app origin is not allowed"
fi
if preflight "http://evil.example" | grep -qi '^access-control-allow-origin:'; then
  fail "the preflight from another origin is allowed"
else
  pass "the preflight from another origin gets no CORS grant"
fi
code="$(post "http://evil.example" "$KEY")"
echo "INFO  a direct (non-browser) POST with another Origin and the key got $code"

# Loki: the vitals and the log arrive, the seeded secret does not.
poll 60 loki_has "{service_name=\"web\"} |= \"$RUN\"" \
  && pass "the Faro log reaches Loki as service web" || fail "no Faro log in Loki"
poll 30 loki_has "{service_name=\"web\"} |= \"web-vitals\" |= \"lcp\"" \
  && pass "Web Vitals reach Loki" || fail "no Web Vitals in Loki"
if loki_lines "{service_name=\"web\"} |= \"$RUN\"" | grep -q "$SECRET"; then
  fail "the seeded secret reached Loki unmasked"
else
  pass "the seeded secret is not in Loki"
fi
loki_has "{service_name=\"web\"} |= \"$RUN\" |= \"redacted\"" \
  && pass "the secret arrived masked" || fail "no redaction marker on the Faro log"

# Tempo: the browser span passes through the same chain.
poll 60 tempo_has "$TRACE_ID" && pass "the Faro trace reaches Tempo" || fail "no Faro trace in Tempo"
tempo_trace "$TRACE_ID" | grep -q "$SESSION" \
  && pass "the Faro session id is a span attribute in Tempo" || fail "session.id missing on the Faro span"

# SEC-002: the spoofed resource is overwritten (web / runtime / dev), the content flags are gone.
code="$(post_ok spoof)"
[[ "$code" =~ ^2 ]] && pass "the spoofed payload is accepted as a normal one ($code)" || fail "the spoofed payload got $code"
spoof_trace_ready() { tempo_trace "$SPOOF_TRACE" | grep -q resourceSpans; }
if poll 60 spoof_trace_ready; then
  tempo_trace "$SPOOF_TRACE" | python3 -c '
import sys, json
t = json.load(sys.stdin)["trace"]
bad = []
for rs in t["resourceSpans"]:
    res = {a["key"]: a["value"].get("stringValue") for a in rs["resource"]["attributes"]}
    want = {"service.name": "web", "service.namespace": "wcl-agent", "app.layer": "runtime",
            "deployment.environment.name": "dev"}
    bad += [f"{k}={res.get(k)}" for k, v in want.items() if res.get(k) != v]
    bad += [k for k in ("content", "app.content") if k in res]
    for ss in rs["scopeSpans"]:
        for sp in ss["spans"]:
            bad += [a["key"] for a in sp.get("attributes", []) if a["key"] in ("content", "app.content")]
print("spoofed:", bad) if bad else None
sys.exit(1 if bad else 0)' \
    && pass "a payload claiming api / claude-code / build / prod lands as web / runtime / dev, content flags removed" \
    || fail "the spoofed resource or a content flag survived"
else
  fail "the spoofed trace never reached Tempo"
fi
loki_has "{service_name=\"web\", app_layer=\"runtime\", deployment_environment_name=\"dev\"} |= \"$RUN\"" \
  && pass "Faro logs carry web / runtime / dev" || fail "Faro logs have another resource"
loki_has "{content=\"true\"} |= \"$RUN\"" \
  && fail "a Faro log reached the content stream" || pass "no Faro log in the content stream"

# SEC-001: the receiver never fetches a stack frame's URL (a listener in the network, appending
# whatever connects to it).
dc exec -T -d grafana sh -c 'rm -f /tmp/faro-sink; while true; do nc -l -p 9999 >> /tmp/faro-sink 2>&1; done'
sleep 1
for PROBE in 1 2 3 4; do
  code="$(post_ok sourcemap)"
  [[ "$code" =~ ^2 ]] || fail "the exception payload got $code"
  sleep 2
done
sleep 6
if [[ "$(dc exec -T grafana sh -c 'cat /tmp/faro-sink 2>/dev/null | wc -c')" -eq 0 ]]; then
  pass "no request reached the listener the stack frames name"
else
  fail "the receiver fetched a stack frame's URL (source map download)"
fi

# SEC-003: bodies over the cap are refused, with or without a Content-Length.
big() { python3 -c 'import sys; sys.stdout.write("{\"pad\": \"" + "x" * 100000 + "\"}")'; }
code="$(big | curl -s -o /dev/null -w '%{http_code}' -X POST "$FARO" -H 'Content-Type: application/json' \
  -H "Origin: $ORIGIN" -H "x-api-key: $KEY" --data-binary @-)"
[[ "$code" =~ ^[45] ]] && pass "a 100 KB body is refused ($code)" || fail "a 100 KB body got $code"
sleep 2
# Known gap (Alloy v1.21.3): the size cap reads Content-Length, so a chunked body (no length) is
# not capped. It is reported, not failed: config cannot close it (see the README).
code="$(big | curl -s -o /dev/null -w '%{http_code}' -X POST "$FARO" -H 'Content-Type: application/json' \
  -H "Origin: $ORIGIN" -H "x-api-key: $KEY" -H 'Transfer-Encoding: chunked' --data-binary @-)"
echo "INFO  KNOWN GAP: a 100 KB chunked body (no Content-Length) got $code; the size cap does not apply to it"
sleep 2

# Rate limit: a burst beyond the configured 10 gets 429s.
limited=0
for _ in $(seq 1 120); do
  [[ "$(post "$ORIGIN" "$KEY")" == 429 ]] && limited=$((limited + 1))
done
(( limited > 0 )) && pass "the rate limit refused $limited of 120 rapid posts" || fail "no post was rate limited"

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
