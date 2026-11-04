# QA triage, sprint 2026-11-04b

Sources: 057 security review (`qa-reports/2026-11-04b/057-security.md`), end sweep (`qa-reports/2026-11-04b-sweep/`), team-lead's live pass on 1c7a931 (board #66, #68, #69).

## Fixed in the sprint
| Finding | Where | Fixed by |
|---|---|---|
| 057 SEC-001 High (source-map SSRF), SEC-002 Med (spoofed resource), SEC-003 Med part (receiver throughput), SEC-006 Low (tokens in URLs) | Faro section, frontend | Tomas, rework before merge (469ec5b) |
| Live #66 / SPEC-001 / PERF-001 / SEC-001 board-to-Loki stuck queue | Alloy, Loki schema | Ansel, 055-qa-fix |
| BUG-002 / SPEC-002 / live #68a ratio stats; live #68b D1 Sessions 0; #68d D1 counts as fractions | build dashboards | Ansel, 055-qa-fix |
| SPEC-009 cc:cache_hit_ratio; PERF-004 content scan; PERF-002 spanmetrics expiration; sweep SEC-002/003 board carve-out and glob; live #69 Gemini Flash prices | Alloy, rules, pricing | Ansel, 055-qa-fix |
| BUG-001 High TTFT start; BUG-003 cache double counts; BUG-005 KB index label; live #68b D7 empty panels; #68c D8 percent axis; #68d D7/D8 counts | agent_runner, cache, search, runtime dashboards | Nils, 056-qa-fix |
| SPEC-004/005/010/011 doc drift | architecture docs, README, telemetry_spec.md | Tomas, docs-2026-11-04b |

## Deferred (Backlog, label qa-deferred unless noted)
| Ticket | Findings |
|---|---|
| Faro shares the Alloy pipeline (sc-458) | 057 SEC-003 rest, PERF-003, PERF-007, chunked bodies (backlog:057-chunked), global rate limit |
| REST trace context skips validation (sc-459) | 057 SEC-004, SEC-005, SPEC-003 |
| Telemetry details (sc-460) | PERF-005, PERF-006, BUG-004 |
| 500 instead of 405 with telemetry on (sc-461) | perf sweep out-of-scope note (054 code) |
| Runtime dashboard follow-ups (sc-462, epic 397, no qa label) | SPEC-008, backlog:runtime-dashboards, Tempo serviceMap datasource |
| PyYAML + Loki sample age (sc-463, epic 397, no qa label) | backlog:055 items 1-2 |
| Breadcrumb on telemetry docs drift (sc-434) | SPEC-006, 007, 010 rest, 012 |
| Breadcrumb on semantic search timeout (sc-428) | live pass; duplicate sc-455 merged and archived |

Not acted on: PERF-008 (Faro bundle, lazy and acceptable), the security report's hardening suggestions (board secret check, spanmetrics cardinality cap, TEAM_BOARD_DIR test isolation). Existing telemetry QA tickets (sc-429..436) were outside this diff-scoped sweep, so "not reported" says nothing about them; no comments added.
