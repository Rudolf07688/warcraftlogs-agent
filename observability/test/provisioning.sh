#!/usr/bin/env bash
# sc-399: the Mimir, Loki and Tempo datasources load from the repository's provisioning
# files on first start, are healthy, and carry the correlation settings: trace -> logs,
# log line (trace_id) -> trace, exemplar -> trace. The clicks themselves are a live check.
# Also Grafana's access settings (anonymous Viewer, admin password, no plugin preinstall).
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
