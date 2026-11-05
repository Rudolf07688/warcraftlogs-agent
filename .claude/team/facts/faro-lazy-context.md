---
id: faro-lazy-context
anchors: [file:frontend/src/telemetry/context.ts, file:frontend/src/telemetry/faro.ts]
by: dev-2 Tomas
source: meta/team/dev-2.md L27; meta/sprints/2026-11-05/board.jsonl #24
verified: b9cf9a3 2026-11-05
---
The Faro packages load only through the dynamic `import()` in `telemetry/faro.ts`, and
`context.ts` imports types only. New Faro-facing code (the socket, the REST client, error
boundaries) calls `context.ts` functions, which are no-ops until `registerFaro`. Never add a
static `@grafana/faro-react` import: it pulls Faro into the main bundle. That is why 060
wrote its own error boundary instead of `FaroErrorBoundary`.
