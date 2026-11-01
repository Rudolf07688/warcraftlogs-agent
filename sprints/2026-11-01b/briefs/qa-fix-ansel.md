# QA fix brief (tier S): 049-qa-fix-lookup — Ansel (dev-1)

From Maren (PO). Sprint 2026-11-01b wrap-up. QA sweep: `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-01b-1615/` (README + performance.md, spec-conformance.md). Fix only what's listed; everything else is deferred to tickets.

- **Branch:** `049-qa-fix-lookup` from `sprint-2026-11-01b` (tip 22c7798, both features merged). Worktree `/home/rudolf/dev/wcl-worktrees/dev-b`: `git -C /home/rudolf/dev/wcl-worktrees/dev-b switch -c 049-qa-fix-lookup sprint-2026-11-01b`.
- **Tier S:** a short plan (board `decision` keyed `scope:049:<topic>`), then implement. No Spec Kit.
- **Parallel:** Nils (dev-3) on `048-qa-fix-kickoff` in dev-a, disjoint files (he has `ws.py` and `wcl_client.py` this round).
- **Security-core:** touches the 039 visibility query; I review the diff myself at hand-off. No new migration unless unavoidable (then `0021`, down `0020_raw_fetch_summary_index`, say so on the board first).

## Fix
1. **Stored-reports lookup is not bounded (PERF-002; sc-324 AC2).** `list_visible_summaries` stops early only after 200 visible rows; a normal workspace has far fewer, so it walks every summary row ever stored and will hit the 2 s timeout as data grows. AC: the scan is bounded by something the index serves (e.g. a lower bound on `fetched_at` matching the visibility window, or start from the workspace's own grants plus public-checked rows), results unchanged for visible rows; a Postgres test shows the bounded plan/rows read; `fetch_visible_clause` stays the one visibility rule and the 039 guard test stays unchanged.
2. **Timing flake (board #73).** `backend/tests/test_raw_store_probe.py::test_every_probe_is_counted_once`: under a slow full run the other-tenant probe exceeds the 400 ms probe timeout, counts as a timeout and opens the 3-in-a-row breaker one call early. Make the first phase immune to load (generous probe timeout there); test-only.
3. **045 spec drift (SPEC-001).** `specs/045-local-data-reads/` (FR-001, US1 scenarios, clarification, plan state diagram) still say one timeout opens the breaker; update to 3 consecutive timeouts or one connection error.

## File footprint
`backend/app/repositories/raw_fetches.py`, `backend/tests/test_raw_store_probe.py`, `backend/tests/test_047_stored_reports*.py` or new `backend/tests/test_049_*.py`, `specs/045-local-data-reads/`. Nothing else.

## Hand-off
Board `handoff` + final result: branch, commits, files, `check.py run --pg ansel` RESULT and RECEIPT (full suite, committed tree, 0 skipped), AC→test mapping, risks. Move nothing on Shortcut.
