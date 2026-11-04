#!/usr/bin/env bash
# Recording rules (feature 055): every rule file loads and evaluates; the cc:* build aliases
# from synthetic Claude Code metrics; genai:cost_usd:rate5m equals tokens x list price for one
# Claude and one Gemini model; after a price change, cost already recorded keeps the old price.
# The rules run from a temporary copy (MIMIR_RULES_DIR), so the price change never touches
# the checkout.
#   observability/test/rules.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
RULES_COPY="$(mktemp -d)"
cp -r "$REPO_ROOT/observability/mimir/rules/." "$RULES_COPY/"
chmod -R a+rX "$RULES_COPY"
export MIMIR_RULES_DIR="$RULES_COPY"
cleanup() { stack_down; rm -rf "$RULES_COPY"; }
trap cleanup EXIT

# Lint with the pinned mimirtool. cost.yaml is left out: its price series keep the name the
# story fixes (llm_price_usd_per_token, no colon), which mimirtool's naming lint rejects;
# the stack check below proves Mimir loads and evaluates it.
for f in build.yaml red.yaml; do
  if docker run --rm -v "$RULES_COPY/anonymous:/r:ro" grafana/mimirtool:3.2.4 rules check "/r/$f" >/dev/null 2>&1; then
    pass "mimirtool rules check $f"
  else
    fail "mimirtool rules check $f"
  fi
done

stack_up
if python3 "$(dirname "$0")/rules_check.py" --otlp "$OTLP" --grafana "$GRAFANA" \
    --pricing "$REPO_ROOT/observability/pricing/pricing.yaml" --cost-rules "$RULES_COPY/anonymous/cost.yaml"; then
  :
else
  FAILURES=$((FAILURES + 1))
fi
if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
