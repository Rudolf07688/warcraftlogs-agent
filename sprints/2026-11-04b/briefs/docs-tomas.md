# Brief: Telemetry 2 docs close-out, tier S

- **Seat:** `dev-2` (Tomas). Fresh run. In parallel: Ansel (dev-1) fixes 055 config in `dev-a` (Loki schema date, timestamp bound in Alloy, dashboard ratios), Nils (dev-3) fixes 056 code in `dev-b`. You touch docs only.
- **Tier S:** a short plan, then implement. Record decisions on the board (key `scope:docs:*`).
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c`. Base: sprint tip `sprint-2026-11-04b` = `1c7a931`. Branch `docs-2026-11-04b` from it.
- **Reports:** `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-04b-sweep/spec-conformance.md` (SPEC-004, SPEC-005, SPEC-010, SPEC-011); board notes `archdocs:056` (#48), `docs:055-fix` (Ansel posts README facts from his fix round there; fold them in if they land before you hand off, otherwise list them as open in your hand-off).

## Do
1. **Architecture docs** (`documentation/architecture/`), procedure in `documentation/architecture/pages/maintaining.html`. `python3 .claude/team/archdocs.py changed` lists the pages whose code moved: agent, backend-api, database, deployment, frontend, knowledge-base, observability, streaming, wcl-data. Re-verify each section against the code at `1c7a931` (the code wins, not the specs): Telemetry 2 content (board into Loki, spanmetrics/servicegraph, Mimir ruler and rule files, pricing, the build and runtime dashboards D1/D2/D6/D7/D8, app metrics, Faro and the receiver, chat trace context in the `ChatTurn` frame, published ports, `open-points.html`'s "none provisioned yet"). Update `index.html` (layer table, system diagram) where a layer changed. Then `archdocs.py stamp` and `archdocs.py check`, and screenshot each changed page with headless google-chrome at 1280 and 390 px to check they render.
2. **`observability/README.md`** (SPEC-004, SPEC-011): `OTEL_*` do not reach a `bin/claude-otel` session's Bash (only `CLAUDE_CODE_ENABLE_TELEMETRY`, `..._BETA` and `TRACEPARENT` do); port list and pipeline summary incl. Faro, board tail, ruler.
3. **`specs/telemetry_spec.md`** (SPEC-010): update §6.5 (native histograms, real label names, `genai:cost_usd:rate5m`, generated price rules), §6.6 (chat context travels in the WebSocket message), §8.3 (the aliases as built) to match the code. Minimal edits; add a dated note line, don't rewrite.

## Footprint
`documentation/architecture/**`, `observability/README.md`, `specs/telemetry_spec.md`. Nothing else.

## Hand-off
Commit, `check.py run --as tomas` (receipt), `archdocs.py check` output, board `handoff` with key `status:docs`, and return branch, head, RESULT/RECEIPT, pages changed. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
