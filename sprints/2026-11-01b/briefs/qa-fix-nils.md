# QA fix brief (tier S): 048-qa-fix-kickoff — Nils (dev-3)

From Maren (PO). Sprint 2026-11-01b wrap-up. QA sweep: `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-01b-1615/` (README + bugs.md, performance.md, security.md). Fix only what's listed; everything else is deferred to tickets.

- **Branch:** `048-qa-fix-kickoff` from `sprint-2026-11-01b` (tip 22c7798, both features merged). Worktree `/home/rudolf/dev/wcl-worktrees/dev-a`: `git -C /home/rudolf/dev/wcl-worktrees/dev-a switch -c 048-qa-fix-kickoff sprint-2026-11-01b`.
- **Tier S:** a short plan (board `decision` keyed `scope:048:<topic>`), then implement. No Spec Kit; update the 046 spec docs where behaviour changes.
- **Parallel:** Ansel (dev-1) on `049-qa-fix-lookup` in dev-b, disjoint files.
- **Security-core:** the lane change sits on the shared WCL client path; I review the diff myself at hand-off.

## Fix
1. **Kickoff turn stuck behind the pre-fetch (PERF-001 = BUG-001 = SEC-001).** The kickoff turn joins the pre-fetch's in-flight background-lane requests and waits on the 2-slot background limit, so the click is slower than without a pre-fetch, up to the 75 s timeout under load. AC: a user-facing (interactive) caller that joins an in-flight request started in the background lane is never held to the background limit (e.g. promote the flight to the interactive lane on join, or equivalent); test with fakes that a joined kickoff call completes without waiting for a background slot, and that background-only work still obeys the background limit.
2. **Empty-answer message pollutes the knowledge base (BUG-002).** When a turn ends with the `empty` outcome, the fixed message is still saved as the reply (keep that), but it is not offered to the knowledge-base indexer and does not drive the chat title or follow-up suggestions. Test it. The runner must tell `ws.py` the outcome (a record or a flag) rather than ws.py string-matching the message.
3. **Compact tables drop nested lists silently (BUG-003).** A compact table that drops or truncates lists nested inside rows (Interrupts/Dispels shapes) counts what it dropped and marks the table truncated when data was left out; a test on an Interrupts-style fixture.
4. Update `specs/046-big-report-turns/` (spec/research/data-model) for the pre-fetch as built (store-reads gate, 10-min cooldown per workspace+report, lane behaviour) — SPEC-002 — and add `empty` to the `TurnStats.outcome` comment (SPEC-006).

## File footprint
`wcl_agent/client/wcl_client.py` (lanes / single-flight join only), `backend/app/services/kickoff_prefetch.py`, `backend/app/agent_runner.py`, `backend/app/api/ws.py` (the final-save path only: indexer/title/suggestions on the empty outcome), `wcl_agent/tools/report_tools.py`, new test files `backend/tests/test_048_*.py`, fixtures under `backend/tests/fixtures/` (new files), `specs/046-big-report-turns/`. Nothing else.

## Hand-off
Board `handoff` + final result: branch, commits, files, `check.py run` RESULT and RECEIPT (full suite, committed tree), AC→test mapping, risks. Move nothing on Shortcut (the stories are already Under Review).
