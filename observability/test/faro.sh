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

# post ORIGIN KEY: the HTTP status of one POST to the receiver.
post() {
  payload | curl -s -o /dev/null -w '%{http_code}' -X POST "$FARO" \
    -H 'Content-Type: application/json' -H "Origin: $1" -H "x-api-key: $2" --data-binary @-
}

code="$(post "$ORIGIN" "$KEY")"
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

# Rate limit: a burst beyond the configured 40 gets 429s.
limited=0
for _ in $(seq 1 120); do
  [[ "$(post "$ORIGIN" "$KEY")" == 429 ]] && limited=$((limited + 1))
done
(( limited > 0 )) && pass "the rate limit refused $limited of 120 rapid posts" || fail "no post was rate limited"

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
