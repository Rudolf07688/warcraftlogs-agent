#!/usr/bin/env bash
# sc-409: spanmetrics and servicegraph series from synthetic spans, with exemplars and no id,
# URL, SQL or session labels; the RED aliases evaluate, and the latency alias leaves out the
# chat WebSocket and the streaming generate routes.
#   observability/test/red.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
trap stack_down EXIT

stack_up
if python3 "$(dirname "$0")/red_check.py" --otlp "$OTLP" --grafana "$GRAFANA"; then
  echo "RESULT PASS"
else
  echo "RESULT FAIL"; exit 1
fi
