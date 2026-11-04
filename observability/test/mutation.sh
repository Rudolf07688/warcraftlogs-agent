#!/usr/bin/env bash
# sc-401 mutation proof: disable one redaction or routing rule at a time and show that
# redaction_check.py then fails. Edits the repo's Alloy files in place and always restores
# them byte for byte (trap), so run it on a clean tree.
#   observability/test/mutation.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
ALLOY_DIR="$REPO_ROOT/observability/alloy"
backup="$(mktemp -d)"
cp -p "$ALLOY_DIR/config.alloy" "$ALLOY_DIR/redact.ottl" "$backup/"
restore() {
  cp -p "$backup/config.alloy" "$backup/redact.ottl" "$ALLOY_DIR/"
  cmp -s "$backup/config.alloy" "$ALLOY_DIR/config.alloy" && cmp -s "$backup/redact.ottl" "$ALLOY_DIR/redact.ottl" \
    || echo "RESTORE FAILED: copy $backup/* back to $ALLOY_DIR" >&2
}
# With KEEP=1 the stack stays up: restart Alloy so it runs the restored config again.
trap 'restore; [[ "${KEEP:-0}" == 1 ]] && reload_alloy; stack_down' EXIT

check() { python3 "$(dirname "$0")/redaction_check.py" --otlp "$OTLP" --grafana "$GRAFANA" >"$backup/out" 2>&1; }

reload_alloy() {
  dc restart alloy >/dev/null
  poll 60 curl -sf -o /dev/null "http://127.0.0.1:${ALLOY_UI_PORT}/-/ready"
  poll 60 curl -sf -o /dev/null "$OTLP/v1/traces" -X POST -H 'Content-Type: application/json' -d '{}'
}

# mutate FILE OLD NEW DESCRIPTION: replace exactly one occurrence, run the check, restore.
mutate() {
  python3 - "$ALLOY_DIR/$1" "$2" "$3" <<'PY' || { fail "mutation not applied ($4)"; return; }
import sys
path, old, new = sys.argv[1:]
text = open(path).read()
if text.count(old) != 1:
    sys.exit(f"expected one occurrence, found {text.count(old)}: {old}")
open(path, "w").write(text.replace(old, new))
PY
  reload_alloy
  if check; then fail "still passes with: $4"; else pass "bites: $4 ($(grep -c '^FAIL' "$backup/out") failing checks)"; fi
  restore
}

stack_up
check && pass "baseline: redaction check passes" || { cat "$backup/out"; fail "baseline fails"; exit 1; }

mutate redact.ottl 'replace_all_patterns(attributes, "value", "eyJ' 'replace_all_patterns(attributes, "value", "NEVER' "JWT mask off in attributes"
mutate redact.ottl '"(?i)(bearer\\s+)' '"(?i)(NEVER\\s+)' "bearer mask off in attributes"
mutate redact.ottl 'replace_all_patterns(attributes, "value", "sk-' 'replace_all_patterns(attributes, "value", "NEVER-' "sk-* mask off in attributes"
mutate redact.ottl 'replace_all_patterns(attributes, "value", "AIza' 'replace_all_patterns(attributes, "value", "NEVER' "AIza* mask off in attributes"
mutate redact.ottl 'replace_all_patterns(attributes, "value", "(postgres' 'replace_all_patterns(attributes, "value", "(NEVER' "DSN mask off in attributes"
mutate redact.ottl 'set(attributes["password"], SHA256(attributes["password"]))' 'set(attributes["password"], attributes["password"])' "password hash off"
mutate config.alloy 'context    = "spanevent"' 'context    = "span"' "span event redaction off"
mutate config.alloy '`replace_pattern(body, "sk-' '`replace_pattern(body, "NEVER-' "sk-* mask off in string log bodies"
mutate config.alloy '`replace_all_patterns(body, "value", "AIza' '`replace_all_patterns(body, "value", "NEVER' "AIza* mask off in map log bodies"
mutate config.alloy 'context    = "resource"
    statements = [
      `delete_matching_keys(attributes, "^(session\\.id|' 'context    = "resource"
    statements = [
      `delete_matching_keys(attributes, "^(NEVER|' "session.id kept on metric resource (target_info)"
mutate config.alloy '`delete_matching_keys(attributes, "^(session\\.id|prompt\\.id|user\\.account_uuid|user\\.email|client_request_id)$")`,
    ]
  }

  output' '`delete_matching_keys(attributes, "^(session\\.id|prompt\\.id|user\\.account_uuid|NEVER|client_request_id)$")`,
    ]
  }

  output' "user.email kept on metric datapoints"
mutate config.alloy 'resource.attributes["service.name"] == "claude-code" and IsMatch(attributes["event.name"], "^(user_prompt|' 'resource.attributes["service.name"] == "claude-code" and IsMatch(attributes["event.name"], "^(NEVER|' "user_prompt not routed to the content stream"

echo "mutation: $FAILURES failure(s)"
[[ $FAILURES == 0 ]] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
