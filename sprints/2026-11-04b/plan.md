# Sprint 2026-11-04b plan: Telemetry 2 (epic 396)

Branch `sprint-2026-11-04b`, base `3262948`. Iteration "Sprint 2026-11-04b" (Shortcut 442). 24 pts, all 9 stories in Shortlist.
Goal: metrics, cost and frontend telemetry, so the owner sees agent-team spend, runtime health and LLM cost, and one chat send end to end.

| Stream | Feature | Dev (seat, model) | Stories in order | Pts |
|---|---|---|---|---|
| A | 055-build-telemetry | Ansel (dev-1, opus medium), dev-a | 407 board→Loki (2), 409 spanmetrics/servicegraph (2), 408 D1/D2 (3), 410 pricing + cost rules (3) | 10 |
| B | 056-runtime-metrics | Nils (dev-3, opus medium), dev-b | 411 ADK metrics (2), 412 app metrics (3), 413 D6–D8 (3) | 8 |
| C | 057-browser-telemetry | Tomas (dev-2, sonnet high), dev-c | 414 Faro + receiver (3), 415 click→Postgres trace (3, WebSocket AC) | 6 |

All tier M. 057 security-core (qa-security at hand-off). Drop order: 410 first, then 413 cut to D7.
Acceptance criteria: verbatim in the briefs (`briefs/055-*.md`, `056-*.md`, `057-*.md`); 415 AC changed on the ticket.
Contracts and owners: board keys `contract:*`, `owner:*` (#9–#21).
Agent ids: ansel ad08000a88e2521ba, nils a3145a4c7e27787c8, tomas a35277d9b5bd1b67c.
