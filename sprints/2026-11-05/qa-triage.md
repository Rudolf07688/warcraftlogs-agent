# QA triage, sprint 2026-11-05 (Maren)

Sources: hand-off review `qa-reports/2026-11-05/058-security.md` (fixed in Ansel's rework before merge), end sweep `qa-reports/2026-11-05-sweep/` on fcef188, team-lead's live pass (board #74-#79).

## Fixed in the one fix round (fresh agents, split by author)
| Finding | Severity | Fixer |
|---|---|---|
| PERF-001 Pyroscope tag leak via never-ended duplicate SQL spans (fixes sc-474, double SQLAlchemy tracer) | Critical | Nils |
| SEC-001 raw request paths in Pyroscope `span_name` labels | Medium | Nils |
| SEC-002 profile tags removed under the renamed name, pile up | Medium | Nils |
| PERF-004 profiler always on without the observability profile | Low | Nils |
| Live #75 two target_info versions per process (backend half) | live FAIL | Nils |
| Live #78 D8 blank when embeddings fail (record failures) | live FAIL | Nils |
| BUG-005 service map `_seconds_sum` copy | Low | Nils |
| SPEC-001 shell boundary outside the router, raw message/stack | High | Tomas |
| SPEC-002 D5 TTFT p95 ungrouped | Medium | Tomas |
| BUG-003 panel boundaries don't reset on conversation switch | Low | Tomas |
| Live #74 D12 attributes 1 of 6 commits | live FAIL | Tomas |
| Live #75 rule prefers a real version; BUG-004 = SPEC-009 topk tie | live FAIL / Low | Tomas |
| SPEC-007, SPEC-008 060 docs drift | Low | Tomas |
| Live #76 Mimir sample_duplicate_timestamp discards | live FAIL | Ansel |
| BUG-001 = SPEC-003 D11 host cgroup dropped | Medium | Ansel |
| Live #77 D9 queryid/__name__ table | live FAIL | Ansel |
| BUG-007 (= SPEC-010 unit part) D9 unit | Low | Ansel |
| SPEC-004 058 docs still describe docker-proxy | Low | Ansel |
| SPEC-005, SPEC-006 telemetry_spec as-built notes, architecture pages | Low | docs pass after the round |

## Deferred (Backlog, label qa-deferred, epic 397)
| Ticket | Findings | Why deferred |
|---|---|---|
| sc-490 | PERF-002 sqlcommenter statement-cache cost | by design, measured at build (board #30); AC requires the commenter |
| sc-491 | BUG-002 + PERF-003 thread-tagged profiles | library limitation, documented; one-user local app |
| sc-492 | SEC-003 e2e skips Pyroscope and Postgres paths | Low; both paths have their own proofs |
| sc-493 | SEC-004 raw browser error text on D5 | Low; loopback Grafana |
| sc-494 | SEC-005 cAdvisor sockets under the general profile | Low; hardened and documented |
| sc-495 | BUG-006 + SEC-006 + SPEC-010 grants: 0022 role reconcile/grants | Low; fails safe (D9 empty) |
| sc-496 | PERF-005..008 collection and query cost | Low |
| sc-480 | 058 review SEC-006 scrape sample/label limits | Low (created at hand-off) |
| sc-481 | pre-existing: backend/frontend ports on all interfaces | pre-existing |
| sc-503 | live re-check #106: D8 records no failure when the 3 s query timeout cancels the call | accepted under the one-rework rule; sc-462's D8 AC met |
| sc-504 | live re-check #106: service-graph node average response time missing/zero (UNCLEAR) | needs steady traffic to judge |

Also from developers' findings (not QA): sc-475 app-side redaction skips resource attributes.

## Existing QA tickets
- sc-471 (dashboard overcount), sc-458, sc-459, sc-460: not reported in this sweep (scoped to the sprint's diff); comment added.
- Duplicates merged: none across tickets; duplicates inside the sweep are grouped above.

## Live re-check (team-lead, on 9a4d860)
- 058-fix PASS (#104), 060-fix PASS (#105), 059-fix PASS except D8 failures (sc-503) and the node-graph average (sc-504) (#106). sc-428 got the 3 s embedding-budget lead.

## Live-pass notes for the owner
- "Build spend per day" alert fires truthfully (138 vs 50 USD threshold): the threshold is the owner's call.
- Failed `wcl` logins on the owner's 5432 at 15:19-15:20 fall in the QA sweep window (performance and bug agents ran reproductions); pg.py/check.py have no 5432 fallback.
