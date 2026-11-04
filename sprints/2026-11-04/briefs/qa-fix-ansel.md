# Brief: QA fix round, telemetry stack (053 follow-up)

- **Branch:** `qa-fix-ansel`, created in your worktree from the sprint tip: `cd /home/rudolf/dev/wcl-worktrees/dev-a && git checkout -b qa-fix-ansel sprint-2026-11-04` (tip `c212475`; your 053 branch is already merged).
- **Tier:** S (short plan, then implement; no Spec Kit). Seat `dev-1` (Ansel). Nils (dev-3) runs a parallel fix round on backend files only.
- **Security-core:** the fixes are security work; make each test bite (mutation).
- **Stories:** follow-ups to the stack, Alloy redaction and claude-otel wrapper stories (sc-398, sc-400, sc-401; they stay Under Review). No ticket moves needed.
- **Sweep reports** (read only the sections named): `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-04-sweep/` security.md, bugs.md, performance.md, spec-conformance.md.

## Fix these (and nothing else)
1. **security SEC-001 / spec SPEC-003 (High): build-layer secrets pass Alloy.** Extend `observability/alloy/redact.ottl` so that captured tool content (span events `tool.output`, `tool_result`/`tool_decision` attributes, log bodies) masks: `NAME=value` / `NAME: value` / JSON `"name": "value"` where NAME matches a sensitive key word (secret, password, passwd, token, key, credential, dsn, auth, cookie, session; case-insensitive, including names like `WCL_CLIENT_SECRET`, `SECRET_KEY`, `APP_DB_PASSWORD`, `ANTHROPIC_API_KEY`); credentials in any `scheme://user:pass@` URL (redis, postgres, http, …); `ya29.` OAuth tokens; GitHub tokens (`gh[pousr]_…`); PEM private-key blocks; lower-case `bearer`. Keep the regexes linear (no nested quantifiers). Add seeds for each shape to `observability/test/redaction_check.py` for both layers and Loki/Tempo, and mutations to `mutation.sh`.
2. **security SEC-003 (Medium): content routing fails open.** For the build layer (`service.name=claude-code`), make the rule fail closed: a Claude Code log record goes to the 7-day content stream unless its event name is on an allowlist of known content-free events (e.g. `api_request`, `api_error`, `subagent_completed`, … check what Claude Code actually emits). Keep `app.content="true"` and `gen_ai.*` routing as is for the runtime layer. Test: an unknown Claude Code event lands in the content stream.
3. **security SEC-002 (Medium) + PERF-003: Grafana.** No anonymous Admin: anonymous role Viewer with Explore still usable (`GF_USERS_VIEWERS_CAN_EDIT=true` or the Grafana 13 equivalent; verify), admin password from `.env` (`GRAFANA_ADMIN_PASSWORD`, no hard-coded default "admin"; if unset, Grafana must not start with `admin/admin` — pick the simplest safe behaviour and document it), plugin preinstall off, `mem_limit` 512m. The port stays on 127.0.0.1.
4. **bugs BUG-001 (Medium): `mutation.sh` edits the live-mounted `redact.ottl`.** Mutations must run on a temporary copy of the Alloy config mounted into the test project only; the checkout's files are never modified, even on a kill.
5. **bugs BUG-002 / SPEC-002 (Medium) + security SEC-006 (Low): `bin/claude-otel`.** Export OTLP over `http/protobuf` to Alloy's HTTP port (4318, overridable), so a backend started from that session exports correctly; validate the port is numeric before it reaches `bash -c`. Re-run `claude-otel.sh`.
6. **SPEC-001 / BUG-006 (Medium): `service.version=unknown` under compose.** Grant: one hunk in `bin/01_start_app.sh` to export `WCL_GIT_SHA=$(git rev-parse --short HEAD)` before `docker compose up`; document in `observability/README.md` that a plain `docker compose up` needs `WCL_GIT_SHA` exported for a real version.
7. **SPEC-005 (Low, banned labels): Claude Code `user.id` / `organization.id`** (and any other user/account id Claude Code emits) are dropped from metric datapoints like the other five ids. Test in the redaction script.

Not in this round (tickets): structural gaps (slices, nested maps, unsalted hashing, SEC-004), unauthenticated receivers (SEC-005), Loki `level` label (SPEC-004), stale 053 spec artefacts (SPEC-007) unless you touch them anyway, the metric datapoint seed test (SPEC-008).

## Footprint
`observability/**`, `docker-compose.yml` (grafana service and alloy only), `bin/claude-otel`, the one hunk in `bin/01_start_app.sh`, `.env.example` (one line documenting `GRAFANA_ADMIN_PASSWORD`; granted for this round, Nils won't touch it). Nothing else.

## Docker
Same grant as before: test projects only (`wcl-obs-test` / `-p wcl-dev-a`), observability services only, `down -v` after each run. The owner's stack (`-p warcraftlogs-agent`) may be running: never touch it or its files.

## Proof and hand-off
All five scripts `RESULT PASS` (`persistence.sh`, `redaction.sh`, `mutation.sh`, `provisioning.sh`, `claude-otel.sh`), the new mutations bite, `check.py run --as ansel` on the committed tree for the receipt. Board `handoff` with key `status:qa-fix-ansel`, and the final result: branch, commits, files, RESULT/RECEIPT lines, script results, a finding-by-finding mapping.
