#!/usr/bin/env bash
# sc-423: secrets seeded through every telemetry path (the build layer shaped like Claude Code,
# the backend's real telemetry bootstrap, the Faro receiver) are never stored unmasked in Loki,
# Tempo or Mimir (redaction_e2e.py). Then the proof that the check bites: one redaction rule
# at a time is disabled in a temporary copy of observability/alloy that only this project
# mounts (ALLOY_CONFIG_DIR, as mutation.sh does), and the check must fail. The checkout's
# files, which a running app stack's Alloy watches, are never written.
#   observability/test/redaction-e2e.sh            (MUTATE=0 skips the mutation runs, KEEP=1 keeps the stack)
# Own stack: COMPOSE_PROJECT / ports as in lib.sh, plus ALLOY_FARO_PORT (default 24347).
source "$(dirname "$0")/lib.sh"
export ALLOY_FARO_PORT="${ALLOY_FARO_PORT:-24347}"
ALLOY_SRC="$REPO_ROOT/observability/alloy"
work="$(mktemp -d)"
export ALLOY_CONFIG_DIR="$work/alloy"
mkdir "$ALLOY_CONFIG_DIR"
cp -p "$ALLOY_SRC"/* "$ALLOY_CONFIG_DIR/"
chmod 755 "$work" "$ALLOY_CONFIG_DIR"
src_sum() { sha256sum "$ALLOY_SRC"/* | sha256sum; }
src_before="$(src_sum)"
finish() { stack_down; rm -rf "$work"; }
trap finish EXIT

check() {
  python3 "$(dirname "$0")/redaction_e2e.py" --otlp "$OTLP" --grafana "$GRAFANA" \
    --faro "http://127.0.0.1:${ALLOY_FARO_PORT}/collect" >"$work/out" 2>&1
}

reload_alloy() {
  dc restart alloy >/dev/null
  poll 60 curl -sf -o /dev/null "http://127.0.0.1:${ALLOY_UI_PORT}/-/ready"
  poll 60 curl -sf -o /dev/null "$OTLP/v1/traces" -X POST -H 'Content-Type: application/json' -d '{}'
}

# mutate FILE OLD NEW DESCRIPTION: one occurrence replaced in the copy, check, copy restored.
mutate() {
  python3 - "$ALLOY_CONFIG_DIR/$1" "$2" "$3" <<'PY' || { fail "mutation not applied ($4)"; return; }
import sys
path, old, new = sys.argv[1:]
text = open(path).read()
if text.count(old) != 1:
    sys.exit(f"expected one occurrence, found {text.count(old)}: {old}")
open(path, "w").write(text.replace(old, new))
PY
  reload_alloy
  if check; then
    fail "still passes with: $4"
  else
    pass "bites: $4 ($(grep -c '^FAIL' "$work/out") failing checks: $(grep '^FAIL' "$work/out" | head -2 | cut -c7- | tr '\n' ';'))"
  fi
  cp -p "$ALLOY_SRC/$1" "$ALLOY_CONFIG_DIR/$1"
}

stack_up
if check; then
  grep -E '^(PASS|FAIL)' "$work/out"
  pass "redaction e2e: no seeded secret stored unmasked on any path"
else
  cat "$work/out"; fail "redaction e2e on the real configuration"
fi

if [[ "${MUTATE:-1}" == 1 && $FAILURES == 0 ]]; then
  mutate redact.ottl 'replace_all_patterns(attributes, "value", "eyJ' 'replace_all_patterns(attributes, "value", "NEVER' "JWT mask off in attributes"
  mutate redact.ottl '"(?i)(bearer\\s+)' '"(?i)(NEVER\\s+)' "bearer mask off in attributes"
  mutate redact.ottl 'replace_all_patterns(attributes, "value", "AIza' 'replace_all_patterns(attributes, "value", "NEVER' "AIza* mask off in attributes"
  mutate redact.ottl '"([A-Za-z][A-Za-z0-9+.-]*://' '"(NEVER://' "URL / DSN password mask off in attributes"
  mutate config.alloy '`replace_pattern(body, "sk-' '`replace_pattern(body, "NEVER-' "sk-* mask off in string log bodies"
  [[ "$(src_sum)" == "$src_before" ]] && pass "checkout's observability/alloy files never written" \
    || fail "checkout's observability/alloy files changed"
fi

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
