#!/usr/bin/env bash
# sc-401: secrets seeded from the build layer (claude-code) and the runtime layer arrive
# hashed or masked in Loki and Tempo, banned identifiers never reach Mimir labels, and
# content events land in the 7-day content stream.
#   observability/test/redaction.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
trap stack_down EXIT

stack_up
if python3 "$(dirname "$0")/redaction_check.py" --otlp "$OTLP" --grafana "$GRAFANA"; then
  echo "RESULT PASS"
else
  echo "RESULT FAIL"; exit 1
fi
