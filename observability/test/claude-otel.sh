#!/usr/bin/env bash
# sc-400: bin/claude-otel sets the spec §5.2 env, passes every argument through to claude
# unchanged, and with Alloy unreachable prints one warning and still starts claude.
# Uses a stub `claude` on PATH, so no real session starts and no Docker is needed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
listener_pid=""
cleanup() { [[ -n "$listener_pid" ]] && kill "$listener_pid" 2>/dev/null; rm -rf "$tmp"; }
trap cleanup EXIT
FAILURES=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILURES=$((FAILURES + 1)); }

cat > "$tmp/claude" <<'STUB'
#!/usr/bin/env bash
printf 'ARG<%s>\n' "$@"
env | grep -E '^(CLAUDE_CODE_|OTEL_)' | sort
STUB
chmod +x "$tmp/claude"

free_port() { python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }

# 1. Alloy down: a port nobody listens on.
down_port="$(free_port)"
out="$(PATH="$tmp:$PATH" ALLOY_OTLP_GRPC_PORT="$down_port" "$REPO_ROOT/bin/claude-otel" -p "two words" --model 'a b' 2>"$tmp/err")" \
  && pass "starts claude with Alloy down (exit 0)" || fail "exit code with Alloy down"
[[ "$(grep -c 'Alloy is not reachable' "$tmp/err")" == 1 ]] && pass "one warning on stderr with Alloy down" \
  || fail "warning missing: $(cat "$tmp/err")"
[[ "$(grep '^ARG' <<<"$out")" == $'ARG<-p>\nARG<two words>\nARG<--model>\nARG<a b>' ]] \
  && pass "arguments passed through unchanged" || fail "arguments: $(grep '^ARG' <<<"$out")"

expect() { grep -qxF "$1" <<<"$out" && pass "env $1" || fail "env $1 missing"; }
expect CLAUDE_CODE_ENABLE_TELEMETRY=1
expect CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
expect OTEL_METRICS_EXPORTER=otlp
expect OTEL_LOGS_EXPORTER=otlp
expect OTEL_TRACES_EXPORTER=otlp
expect OTEL_EXPORTER_OTLP_PROTOCOL=grpc
expect "OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:$down_port"
expect OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative
expect OTEL_METRIC_EXPORT_INTERVAL=10000
expect OTEL_METRICS_INCLUDE_VERSION=true
expect OTEL_METRICS_INCLUDE_ENTRYPOINT=true
expect OTEL_METRICS_INCLUDE_REPOSITORY=true
expect OTEL_LOG_TOOL_DETAILS=1
expect OTEL_LOG_USER_PROMPTS=1
expect OTEL_LOG_ASSISTANT_RESPONSES=1
expect OTEL_LOG_TOOL_CONTENT=1
expect OTEL_RESOURCE_ATTRIBUTES=service.namespace=wcl-agent,app.layer=build,deployment.environment.name=dev

# 2. Alloy up: something listens, so no warning.
up_port="$(free_port)"
python3 -c 'import socket,sys,time; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1", int(sys.argv[1]))); s.listen(); time.sleep(60)' "$up_port" &
listener_pid=$!
for _ in $(seq 1 50); do (: > "/dev/tcp/127.0.0.1/$up_port") 2>/dev/null && break; sleep 0.1; done
PATH="$tmp:$PATH" ALLOY_OTLP_GRPC_PORT="$up_port" "$REPO_ROOT/bin/claude-otel" --version >/dev/null 2>"$tmp/err2" \
  && [[ ! -s "$tmp/err2" ]] && pass "no warning with Alloy reachable" || fail "unexpected stderr: $(cat "$tmp/err2")"

echo "claude-otel: $FAILURES failure(s)"
[[ $FAILURES == 0 ]] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
