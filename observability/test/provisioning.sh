#!/usr/bin/env bash
# sc-399: the Mimir, Loki and Tempo datasources load from the repository's provisioning
# files on first start, are healthy, and carry the correlation settings: trace -> logs,
# log line (trace_id) -> trace, exemplar -> trace. The clicks themselves are a live check.
#   observability/test/provisioning.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
trap stack_down EXIT

stack_up

for uid in mimir loki tempo; do
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

# Both links need trace_id on the stored record, so check one end to end.
trace_id="$(hex 16)"; marker="prov-$(hex 4)"
post_otlp logs '{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"provisioning-test"}}]},"scopeLogs":[{"logRecords":[{"timeUnixNano":"'"$(now_ns)"'","body":{"stringValue":"'"$marker"'"},"traceId":"'"$trace_id"'","spanId":"'"$(hex 8)"'"}]}]}]}'
# The query trace -> logs runs, with the service tag filled in as Grafana does.
poll 120 loki_has "{service_name=\"provisioning-test\"} | trace_id=\"$trace_id\"" \
  && pass "stored log found by its trace_id structured metadata" || fail "trace_id not on the stored log"

echo "provisioning: $FAILURES failure(s)"
[[ $FAILURES == 0 ]] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
