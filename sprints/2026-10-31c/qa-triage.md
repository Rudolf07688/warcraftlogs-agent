# QA triage, sprint 2026-10-31c (Maren, PO)

The sweep covered `a5b84de..5550997`, i.e. the merged features 039 and 040, with all four
auditors. Reports are in `qa-reports/2026-10-31c/` (sprint worktree, gitignored). Totals:
0 Critical, 2 High, 12 Medium, 10 Low. Many findings overlap; there are five root causes.

## Fixed in the one rework round (041 Ansel, 042 Tomas)

The fixes went to each author: the crucial findings sit in two disjoint codebases, and each author already had the context (board #41).

| Root cause | Findings | Why it's crucial | Fix |
|---|---|---|---|
| Gone detection deletes reports that still exist | BUG-001 (High), BUG-002, BUG-003, BUG-007, SEC-002, SPEC-003, PO note #40 | Data loss in new code; any hand-written query could purge any report | 041 |
| Grants follow the query text, not the response | SEC-001 (High), SPEC-001, BUG-005 | It breaks sc-178 AC1: a tenant could read another tenant's copy of a report it never fetched | 041 |
| Writer batch timeout drops a whole batch | BUG-004, PERF-003, SPEC-004, SEC-003, PERF-008 | A correctness regression in new code: up to 20 writes, including deletions, are lost at once | 041 |
| Interrupted turns never link their charts | SPEC-002 | It breaks sc-213 AC1/AC2; it's the real root cause the story was looking for | 042 |
| Scroll-to-question releases the stick-to-bottom lock | BUG-006 | A regression: the next turn isn't followed on screen | 042 |

## Deferred (labelled `qa-deferred`)

Each finding was compared by meaning (IDs, paths, symptoms) against the open Team 1 QA tickets
read during planning (sc-156 to sc-277).

| Ticket | Action | Findings | Pts |
|---|---|---|---|
| sc-295 (new) | created | PERF-001, PERF-002, PERF-004, PERF-005, PERF-006, PERF-007: store probe and writer cost, no breaker, no counters | 3 |
| sc-296 (new) | created | Ansel's `backlog:raw-store-redis-backfill`, plus the two unconfirmed races in `bugs.md` (stale write after gone; Redis refill after eviction) | 2 |
| sc-297 (new) | created | PERF-009: the both-limited budget counts only sleep time | 1 |
| sc-275 | breadcrumb ("Last seen 2026-11-01") | SPEC-005: README, ai_guide and `.env.example` don't mention store reads or the two new settings | — |
| sc-270 | breadcrumb | PERF-002's set_config pair is the same pattern at a new site (tracked in sc-295) | — |
| sc-132 | breadcrumb | PERF-007's counters are the first step of hit-rate tracking | — |

There were no duplicates to merge and nothing was archived.

## "Not reported" comments

None. The sweep was scoped to the sprint diff. The open QA tickets outside it weren't re-checked, so a "Not reported" comment would claim a check that never happened.

## Fix-round outcome

- **042** (Tomas, merged at b289f66):
  - Every interrupted turn now links its charts: to the partial agent message, or to the turn's own user message when no agent message was saved. A later answer can't claim them.
  - The stick-to-bottom lock re-engages when a new turn starts.
  - Backend 1452 passed, frontend 65/65. He also found that proposals have the same gap as the charts; that's now sc-301 (1 pt, `qa-deferred`).
- **041** (Ansel, merged at 6dd57e7):
  - A report is deleted as gone only when our own `REPORT_SUMMARY` gets back `report: null`, and only if every error sits at the report path itself and says not-found or permission.
  - Grants come only from a report that came back non-null. That means our summary queries, or a plain single-report query whose response really starts with that report.
  - A batch that times out is retried one item at a time. Batches are capped at 20 items and 8 MB, and the Redis eviction runs after the timed DB part.
  - SQLite 1472 passed; Postgres 83 passed (PO run). Bypass attempts by Ansel (#53) and Maren (#56) both held.
- **The gap that remains is by design:** a table-only flow notices that a report went private only at the 1-day re-check, because only the summary query can trigger a delete (tracked with sc-296).
