#!/usr/bin/env bash
# sc-424: the two Grafana-managed alert rules (provisioning/alerting/rules.yaml) each go Firing on a
# synthetic trigger and back to Normal. Build spend: synthetic Claude Code cost with the threshold
# lowered, then raised again, in a temporary copy of the rules (MIMIR_RULES_DIR; the checkout is
# never touched). Pipeline: a log record Loki refuses for good (two hours behind its stream).
#   observability/test/alerts.sh        (KEEP=1 leaves the stack up; takes about 8 minutes)
source "$(dirname "$0")/lib.sh"
RULES_COPY="$(mktemp -d)"
cp -r "$REPO_ROOT/observability/mimir/rules/." "$RULES_COPY/"
chmod -R a+rX "$RULES_COPY"
export MIMIR_RULES_DIR="$RULES_COPY"
cleanup() { stack_down; rm -rf "$RULES_COPY"; }
trap cleanup EXIT

stack_up
if python3 "$(dirname "$0")/alerts_check.py" --otlp "$OTLP" --grafana "$GRAFANA" \
    --rules "$RULES_COPY/anonymous/datastores.yaml"; then
  :
else
  FAILURES=$((FAILURES + 1))
fi
if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
