# Fix brief (tier S): 060 sweep + live-pass fixes, Tomas

- **Seat:** `dev-2` (Tomas). Parallel fixers: Ansel (dev-1, 058 fixes), Nils (dev-3, 059 fixes). Board keys bind you.
- **Tier:** S (short plan, then implement; no Spec Kit). Branch `060-fix` from the sprint tip `sprint-2026-11-05` = `fcef188`, in worktree `/home/rudolf/dev/wcl-worktrees/dev-c`.
- **Security-core:** no. Reports: `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-05-sweep/{spec-conformance,bugs}.md` and board #74, #75.
- **Migration:** none.

## Fix these (each with a test that bites)
1. **High, the shell boundary never catches (spec-conformance.md).** It sits outside `RouterProvider` (`frontend/src/main.tsx:74`) and no route has `errorElement`, so React Router's default page shows the raw message and stack for any route render error (App outside the panels, profile, admin, login) and nothing reaches Faro. Route errors must render the same plain fallback (never message or stack) and report to Faro with route and boundary. Test with a thrown route element.
2. **Medium, D5 "Client TTFT p95" isn't a p95.** `quantile_over_time(...)` without `by ()` (`frontend.json:220`) gives one tile per event. Aggregate correctly; make `frontend.sh` send several events so the test would catch it. Check D5's other Loki stats for the same shape.
3. **Low, panel fallback survives a conversation switch (bugs.md).** Give the chat panel boundaries a reset key (the conversation id) so a new conversation starts clean.
4. **Live FAIL #74, D12 attributes 1 of 6 commits.** `observability/build-runtime/commits.py` reads only `status:<feature>` keys and SHAs in refs. Accept `merge:<feature>` too, and fall back to `head <sha>` / a SHA in the text when refs is empty. Test it against this sprint's real board export (`python3 .claude/team/board.py log` output; don't modify the board).
5. **Live FAIL #75 (your half).** Nils fixes the second Resource; make `cross:running_version:info` prefer a version other than `unknown` too, so a stray series can't hide the real one. Also fix the "latest push wins" `topk` tie (bugs.md/spec Low: every `build_commit_info` value is 1) so the rule is deterministic, and its comment true.
6. **Docs drift (spec-conformance.md Lows).** `specs/060-frontend-build-runtime/tasks.md` ticks a test file that doesn't exist and leaves T019 unchecked; the spec/README/e2e text still promise a Postgres row the PO dropped (board #67). Make them say what was built.

## Footprint
`frontend/src/**`, `observability/grafana/dashboards/runtime/frontend.json`, `observability/grafana/dashboards/cross/**`, `observability/mimir/rules/anonymous/cross.yaml`, `observability/build-runtime/**`, `observability/test/{frontend.sh,build-runtime.sh,redaction-e2e.sh,redaction_e2e.py}`, `backend/tests/test_telemetry_cross_dashboards.py`, `observability/README.md` (060 section), `specs/060-frontend-build-runtime/**`. Nothing else.

## Proof and hand-off
`check.py run --as tomas` (receipt), `cd frontend && npm run build && npm test`. Stack runs only as before (`wcl-obs-tomas`, 26xxx, `down -v`). Board `handoff` + final result: branch, commits, RESULT/RECEIPT and frontend lines, finding-by-finding mapping. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
