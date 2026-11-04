#!/usr/bin/env bash
# sc-398: a span, a log and a metric sent while the backends are stopped (and Alloy is
# restarted, so only the disk queue can hold them) show up after the backends start.
# Also asserts the retention settings the backends actually run with.
#   observability/test/persistence.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
trap stack_down EXIT

stack_up
echo "stack up ($COMPOSE_PROJECT); stopping ${BACKENDS[*]}"
dc stop "${BACKENDS[@]}" >/dev/null

run="p$(hex 4)"
trace_id="$(hex 16)"
span_id="$(hex 8)"
t="$(now_ns)"
res='{"attributes":[{"key":"service.name","value":{"stringValue":"persistence-test"}}]}'

post_otlp traces '{"resourceSpans":[{"resource":'"$res"',"scopeSpans":[{"spans":[{"traceId":"'"$trace_id"'","spanId":"'"$span_id"'","name":"queued-span","kind":1,"startTimeUnixNano":"'"$t"'","endTimeUnixNano":"'"$t"'"}]}]}]}'
post_otlp logs '{"resourceLogs":[{"resource":'"$res"',"scopeLogs":[{"logRecords":[{"timeUnixNano":"'"$t"'","severityText":"INFO","body":{"stringValue":"queued log '"$run"'"},"traceId":"'"$trace_id"'","spanId":"'"$span_id"'"}]}]}]}'
post_otlp metrics '{"resourceMetrics":[{"resource":'"$res"',"scopeMetrics":[{"metrics":[{"name":"persistence_test_'"$run"'","gauge":{"dataPoints":[{"timeUnixNano":"'"$t"'","asDouble":1}]}}]}]}]}'
echo "sent span, log, metric (run $run) with backends down"

sleep 5
dc restart alloy >/dev/null
echo "restarted alloy; starting backends"
dc start "${BACKENDS[@]}" >/dev/null

poll 240 tempo_has "$trace_id" && pass "span arrived in Tempo after restart" || fail "span not in Tempo"
poll 240 loki_has "{service_name=\"persistence-test\"} |= \"queued log $run\"" \
  && pass "log arrived in Loki after restart" || fail "log not in Loki"
poll 240 mimir_has "persistence_test_$run" && pass "metric arrived in Mimir after restart" || fail "metric not in Mimir"

# Retention as the backends run it (spec §10, §14 decision 9).
loki_cfg="$(backend_get http://loki:3100/config)"
grep -q 'retention_period: 30d' <<<"$loki_cfg" && grep -q 'retention_enabled: true' <<<"$loki_cfg" \
  && pass "Loki keeps logs 30 days" || fail "Loki retention"
grep -A3 'retention_stream:' <<<"$loki_cfg" | tr -d '\n' | grep -q "period: 1w.*selector: '{content=\"true\"}'" \
  && pass "Loki keeps the content stream 7 days" || fail "Loki content retention_stream"
backend_get http://tempo:3200/status/config | grep -q 'block_retention: 168h0m0s\|block_retention: 1w' \
  && pass "Tempo keeps traces 7 days" || fail "Tempo retention"
backend_get http://mimir:9009/config | grep -q 'compactor_blocks_retention_period: 395d10h\|compactor_blocks_retention_period: 9490h' \
  && pass "Mimir keeps metrics ~13 months" || fail "Mimir retention"

echo "persistence: $FAILURES failure(s)"
[[ $FAILURES == 0 ]] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
