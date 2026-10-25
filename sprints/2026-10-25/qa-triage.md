# QA triage, sprint 2026-10-25

Sweep: `/qa-sweep` (all four agents) over the sprint diff `4923785..bff3d31`, run from
`/home/rudolf/dev/wcl-worktrees/sprint`. Reports: `qa-reports/2026-10-25/` (README.md is
the index). Totals: 0 Critical, 2 High, 5 Medium, 19 Low. Tests at bff3d31: 1060 passed /
3 skipped / 1 deselected. The frontend type check is clean.

I spot-checked FN-1 to FN-3 in the code myself.

## Fix now (crucial)

| # | Findings | Why it's crucial | Owner area | Status |
|---|---|---|---|---|
| FN-1 | SPEC-001 (High) + BUG-002 (Medium) | A broken acceptance criterion: 022 AC 1 and 4 (FR-010). Stored M+ runs vanish for raid-less players while a refresh runs or after it fails, and an M+ fetch error fails the whole refresh. This hits the dungeon-only player the feature exists for. | fix feature X (022 area) | sent to scrum master |
| FN-2 | SPEC-002 (Medium) | A broken decision (19): every run names all own characters in the report, not the ones in the key. It's visible and misleading. | fix feature X | sent |
| FN-3 | BUG-001 (Medium) | Data correctness: the `legacy` backfill does nothing under FORCE RLS for a non-superuser migrator, so every existing chat would get auto-renamed (019 AC 6, decision 13). It's masked locally because compose migrates as a superuser. The fix is two statements. | fix feature Y (migration and docs) | sent |
| FN-4 | SPEC-003, 004, 005, 007, 008, 009 (Low, docs) | A release deliverable: README and ai_guide describe pre-sprint behaviour, and specs and task lists contradict the accepted decisions. Docs only, cheap while the fix devs are in the area. SPEC-006 (missing 022 test assertions) is closed by FN-1's tests. | X (022 docs) and Y (the rest) | sent |

Re-verification after the fixes merge: I check each item against its finding, re-run pytest
and the build, and re-run the spec and bugs QA agents on the fix diff.

## Deferred: board changes (owner rule 2026-10-25: no duplicates, `qa-deferred`, ranked below non-QA work)

I compared each deferred finding with the existing QA tickets (sc-156, 157, 158, 159; label
`qa-deferred` and "QA" in the name). **None matched by meaning**, so there were no updates
and no merges. Related findings within this sweep went into one ticket each.

### Created (Backlog, type bug, `qa-deferred`, Priority Lowest, First/Last seen 2026-10-25)

| Ticket | Findings | Est | Labels |
|---|---|---|---|
| sc-176 QA PERF-001: switch to the sibling model sooner on 429s | PERF-001 (High; conforms to AC 1 as written, so it's an improvement), plus the security note "one wait budget per turn" | 2 | ai, performance |
| sc-177 QA PERF-002/PERF-003/SEC-003: raw_fetches write amplification, unbounded growth and writer edge cases | PERF-002, PERF-003, SEC-003, plus the bug leads on column widths, NUL, the throttle count and params in error logs | 3 | data, performance |
| sc-178 QA SEC-001: guard raw_fetches against cross-tenant exposure before anything reads it | SEC-001 | 2 | security, data |
| sc-179 QA BUG-003/SEC-002: harden generated-title cleaning | BUG-003, SEC-002 (SPEC-007's doc is fixed in FN-4) | 2 | ai, backend, security |
| sc-180 QA BUG-005/PERF-006/PERF-007: conversation-list state | BUG-005, PERF-006, PERF-007, plus the unhandled-rejection lead | 2 | ui, performance |
| sc-181 QA BUG-004: sidebar "last activity" order is first-message order | BUG-004 (predates the sprint) | 1 | backend, ui |
| sc-182 QA PERF-004/PERF-005: make the welcome M+ refresh step cheaper | PERF-004, PERF-005 | 2 | backend, performance |
| sc-183 QA BUG-LEAD-022: welcome M+ edge cases | bug leads: same key in two reports, double-click, unlinked run; security hardening: fight_id bounds, control characters in the dungeon name | 2 | backend, ui |
| sc-184 QA BUG-LEAD-021: web search after a model fallback may surface raw provider errors | bug lead (unconfirmed) | 2 | ai |
| sc-185 QA SEC-HARDEN-2026-10-25: Postgres-backed tenant-isolation tests and composite tenant FKs | security hardening (Postgres RLS tests in CI, composite FKs); BUG-001's root cause | 3 | security, infra |

### Updated

- sc-129 (DB-first reads, not a QA ticket): a design-gate comment pointing to sc-178 and
  sc-177.

### Existing QA tickets not reported in this sweep (breadcrumb added, left open)

- sc-156, sc-159: the discovery code was only moved, not changed, so they weren't
  re-checked. sc-159's breadcrumb gives the new paths.
- sc-157, sc-158: excluded from the security agent's scope as already ticketed. The
  agent confirmed the sprint didn't make them worse. sc-158 keeps its "pull forward
  before sc-146" reminder.

### Merges

None. No duplicate QA tickets exist.

### Not ticketed (not worth keeping)

- PERF-008: a one-time cold summary cache after the `:keystone` key bump, plus about 5–10%
  larger summaries. Noted for the owner's live test.
- PERF-009: the title job and the follow-up suggestions call the same helper model at the
  same moment. Negligible at current scale.
- Live-only unknowns: WCL `kill` semantics for depleted keys, the cost of the 4 fields,
  and the Gemini signature bypass. These are owner live-test items, not tickets.

## Re-check after the fixes (2026-10-25)

Reports: `qa-reports/2026-10-25-recheck/` (spec-conformance.md, bugs.md), at sprint head
c06e514. Tests: 1064 passed / 3 skipped / 1 deselected; tsc clean.

| Finding | Verdict |
|---|---|
| SPEC-001 / BUG-002 (FN-1) | Fixed. QA cancel/timeout script plus the new tests. |
| SPEC-002 (FN-2) | Fixed |
| BUG-001 (FN-3) | Fixed. QA re-ran it on Postgres 17 with a non-superuser owner, including a rollback on failure. |
| SPEC-004, 005, 006, 007, 008, 009 (FN-4 / FN-1 tests) | Fixed |
| SPEC-003 (FN-4) | Partially fixed: README lacks feature 020 (raw_fetches, the `WCL_FETCH_PERSIST_*` settings) |

New findings from the fixes:
- **FN-5 (docs only), first marked fix now, then deferred by the owner's ruling (no new fix
  round unless critical): created qa-deferred sc-193.** Original note: SPEC-003 remainder; SPEC-R01 (ai_guide §18 must say that an
  M+-only failure is logged and the refresh records `succeeded`, per decision 36, or a
  future agent may "fix" it and bring back SPEC-001); SPEC-R02 (the 023 checkpoint should
  attribute `106.25%` to 8a8ce50, not 0c62d18). Fix now because SPEC-R01 guards against a
  regression and all three are one-line doc edits.
- **Deferred, update:** BUG-R01, R02, R03 and the WelcomePanel test gap went to **sc-183** as
  a dated breadcrumb, matched by meaning: welcome M+ edge cases. The missing Postgres test
  for BUG-001's failure mode went to **sc-185** as a breadcrumb. No new tickets, no merges.
- **Product ruling on BUG-R03:** the next due refresh retries an M+-only failure. That's
  accepted for this sprint (it extends decision 36), and options are noted on sc-183.

**Final gate (owner ruling, 2026-10-25):** PASS. FN-1 to FN-4 are verified fixed, and tests
(1064/3/1) and the build are green at c58b281. FN-5 is cancelled and became qa-deferred
**sc-193** (1 pt, Lowest). New since the first sweep: one ticket (sc-193) and two
breadcrumbs (sc-183, sc-185).

**Update:** FN-5 was done in 9636d39 (scrum master, no gate). sc-193 is covered by that commit and is now Under Review. Final head: 0711283.
