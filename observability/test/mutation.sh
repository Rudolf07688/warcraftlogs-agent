#!/usr/bin/env bash
# sc-401 mutation proof: disable one redaction, label or routing rule at a time and show that
# redaction_check.py then fails. The rules are mutated in a temporary copy of
# observability/alloy that only this test project mounts (ALLOY_CONFIG_DIR): the checkout's
# files, which a running app stack's Alloy watches and reloads, are never written, even when
# the script is killed.
#   observability/test/mutation.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
ALLOY_SRC="$REPO_ROOT/observability/alloy"
work="$(mktemp -d)"
export ALLOY_CONFIG_DIR="$work/alloy"
mkdir "$ALLOY_CONFIG_DIR"
cp -p "$ALLOY_SRC"/* "$ALLOY_CONFIG_DIR/"
chmod 755 "$work" "$ALLOY_CONFIG_DIR"
src_sum() { sha256sum "$ALLOY_SRC"/* | sha256sum; }
src_before="$(src_sum)"

restore() { cp -p "$ALLOY_SRC/config.alloy" "$ALLOY_SRC/redact.ottl" "$ALLOY_CONFIG_DIR/"; }
finish() {
  if [[ "${KEEP:-0}" == 1 ]]; then
    restore; reload_alloy  # the kept stack runs the unmutated rules (copy left in $work)
  fi
  stack_down
  [[ "${KEEP:-0}" == 1 ]] || rm -rf "$work"
}
trap finish EXIT

check() { python3 "$(dirname "$0")/redaction_check.py" --otlp "$OTLP" --grafana "$GRAFANA" >"$work/out" 2>&1; }

reload_alloy() {
  dc restart alloy >/dev/null
  poll 60 curl -sf -o /dev/null "http://127.0.0.1:${ALLOY_UI_PORT}/-/ready"
  poll 60 curl -sf -o /dev/null "$OTLP/v1/traces" -X POST -H 'Content-Type: application/json' -d '{}'
}

# mutate FILE OLD NEW DESCRIPTION: replace exactly one occurrence in the copy, run the check,
# restore the copy.
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
  if check; then fail "still passes with: $4"; else pass "bites: $4 ($(grep -c '^FAIL' "$work/out") failing checks)"; fi
  restore
}

stack_up
check && pass "baseline: redaction check passes" || { cat "$work/out"; fail "baseline fails"; exit 1; }

KEYWORDS='(?:secret|passw(?:or)?d|token|key|credential|dsn|auth|cookie|session)'
URL_RULE='"([A-Za-z][A-Za-z0-9+.-]*://'
LABELS='^(session\\.id|ccr\\.session\\.id|prompt\\.id|user\\.id|user\\.account_uuid|user\\.account_id|user\\.email|user\\.groups|organization\\.id|client_request_id)$'

# Attribute rules (redact.ottl: resource, span, span event, log and datapoint attributes).
mutate redact.ottl 'replace_all_patterns(attributes, "value", "eyJ' 'replace_all_patterns(attributes, "value", "NEVER' "JWT mask off in attributes"
mutate redact.ottl '"(?i)(bearer\\s+)' '"(?i)(NEVER\\s+)' "bearer mask off in attributes"
mutate redact.ottl '"(Basic\\s+)' '"(NEVER\\s+)' "Basic mask off in attributes"
mutate redact.ottl 'replace_all_patterns(attributes, "value", "sk-' 'replace_all_patterns(attributes, "value", "NEVER-' "sk-* mask off in attributes"
mutate redact.ottl 'replace_all_patterns(attributes, "value", "AIza' 'replace_all_patterns(attributes, "value", "NEVER' "AIza* mask off in attributes"
mutate redact.ottl '"ya29\\.' '"NEVER\\.' "ya29. mask off in attributes"
mutate redact.ottl '"(gh[pousr]_|github_pat_)' '"(NEVER_|NEVER2_)' "GitHub token mask off in attributes"
mutate redact.ottl '"-----BEGIN [A-Z ]*PRIVATE' '"-----NEVER [A-Z ]*PRIVATE' "PEM private key mask off in attributes"
mutate redact.ottl "$URL_RULE" '"(NEVER://' "URL password mask off in attributes"
mutate redact.ottl "$KEYWORDS" '(?:NEVER)' "NAME=value / JSON pair mask off in attributes"
mutate redact.ottl 'set(attributes["password"], SHA256(attributes["password"]))' 'set(attributes["password"], attributes["password"])' "password hash off"
mutate config.alloy 'context    = "spanevent"' 'context    = "span"' "span event redaction off"
# Log body rules (config.alloy), string and map bodies.
mutate config.alloy '`replace_pattern(body, "sk-' '`replace_pattern(body, "NEVER-' "sk-* mask off in string log bodies"
mutate config.alloy '`replace_pattern(body, "-----BEGIN' '`replace_pattern(body, "-----NEVER' "PEM mask off in string log bodies"
mutate config.alloy "\`replace_pattern(body, \"(?i)([A-Za-z0-9_.-]*$KEYWORDS" "\`replace_pattern(body, \"(?i)([A-Za-z0-9_.-]*(?:NEVER)" "pair mask off in string log bodies"
mutate config.alloy '`replace_all_patterns(body, "value", "AIza' '`replace_all_patterns(body, "value", "NEVER' "AIza* mask off in map log bodies"
mutate config.alloy "\`replace_all_patterns(body, \"value\", $URL_RULE" '`replace_all_patterns(body, "value", "(NEVER://' "URL password mask off in map log bodies"
# Banned metric labels.
mutate config.alloy "context    = \"resource\"
    statements = [
      \`delete_matching_keys(attributes, \"^(session\\\\.id|" "context    = \"resource\"
    statements = [
      \`delete_matching_keys(attributes, \"^(NEVER|" "session.id kept on metric resource (target_info)"
mutate config.alloy "\`delete_matching_keys(attributes, \"$LABELS\")\`,
    ]
  }

  output" "\`delete_matching_keys(attributes, \"${LABELS/user\\\\.email/NEVER}\")\`,
    ]
  }

  output" "user.email kept on metric datapoints"
mutate config.alloy "\`delete_matching_keys(attributes, \"$LABELS\")\`,
    ]
  }

  output" "\`delete_matching_keys(attributes, \"${LABELS/|user\\\\.id|/|NEVER|}\")\`,
    ]
  }

  output" "Claude Code user.id kept on metric datapoints"
mutate config.alloy "\`delete_matching_keys(attributes, \"$LABELS\")\`,
    ]
  }

  output" "\`delete_matching_keys(attributes, \"${LABELS/organization\\\\.id/NEVER}\")\`,
    ]
  }

  output" "Claude Code organization.id kept on metric datapoints"
# Content routing.
mutate config.alloy '`set(attributes["alloy.content_stream"], "true")`,' '`set(attributes["alloy.content_stream"], "false")`,' "content flag defaults to false (fail open)"
mutate config.alloy '"^(api_request|api_refusal|' '"^(brand_new_event|api_request|api_refusal|' "unknown Claude Code event allowlisted"
mutate config.alloy ' or resource.attributes["app.layer"] == "build")' ')' "build layer known by service.name only"

[[ "$(src_sum)" == "$src_before" ]] && pass "checkout's observability/alloy files never written" \
  || fail "checkout's observability/alloy files changed"

echo "mutation: $FAILURES failure(s)"
[[ $FAILURES == 0 ]] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
