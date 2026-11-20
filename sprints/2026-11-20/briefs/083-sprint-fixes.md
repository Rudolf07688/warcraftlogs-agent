# Brief 083-sprint-fixes (dev-3 Nils, QA fix round)

- **Feature / branch:** 083 / `083-sprint-fixes`
- **Tier:** S (six small fixes, in the order below). **Model / effort:** opus, medium.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-e` (new branch from the base). **Base ref:** sprint-2026-11-20 tip at launch (`git -C /home/rudolf/dev/wcl-worktrees/sprint rev-parse sprint-2026-11-20`).
- **Seat:** dev-3 (Nils). Nobody else is building.
- **Security-core:** no. **Migration:** none.
- Triage: `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-11-20/qa-triage.md`; reports in
  `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-20/` (spec-conformance.md SPEC-001..004, L5; bugs.md BUG-001..003). Read the finding, not the whole report.

## Fixes (each: one test where the fix takes effect, then the fix)
1. **F1, SPEC-001 High (sc-571 AC; live FAIL 2/2 on Claude haiku):** "The Ula'tek heart" no longer reaches `get_boss_mechanics`, because 082's `<CONTEXT_RESOLUTION>` default rule uses "the Ula'tek heart" as its example of a vague log request (`wcl_agent/agent.py` ~159). Make "boss name + an ability, phase or part word" a mechanic question first: call `get_boss_mechanics` with that word, then tie it to the newest kill per the default rule (sc-575's own example: "I took your newest kill on Ula'tek and looked at the Heart phase"). Replace the example; don't add a second contradicting rule.
2. **F2, SPEC-002 + spec L5:** restore the `<PERSONALITY>` sentence "Settle the facts, confidence, and fixes first; then voice them." and "or unrelated" in the known-players narrowing rule ("population-level or unrelated questions"), both removed by 082 out of scope. Prompt budget: test_064 must stay green (FIXED_BUDGET is never raised); if tight, trim your own 082 wording, not other sections.
3. **F3, BUG-001 (sc-575 AC):** `profile_context` class fill compares realms as lower-cased text, so "Tarren Mill" never matches a known player on "tarren-mill" (`backend/app/services/profile_context.py:66,291`). Compare by the same realm slug the rest of the app uses (reuse the existing slug helper; don't write a new one). Test with exactly that pair.
4. **F4, BUG-002 (sc-571):** `get_boss_mechanics("Venomous Heart", "Ula'tek (Mythic)")` and `"Mythic Ula'tek"` return found:false although the note exists (`backend/app/agent_tools/mechanics.py:144`). Ignore difficulty words (LFR/Normal/Heroic/Mythic, in or out of brackets) when matching the encounter. Keep every 081 hostile-input test green.
5. **F5, SPEC-003 (078 regression):** `raid_summary.part_keys` only looks up whole-report participants under the new `startTime/endTime` key; rows stored before this sprint under the old `playerDetails(fightIDs: $fightIDs)` + `fightIDs: null` key are no longer found (`backend/app/services/raid_summary.py` ~148-153). Add the legacy key as a read-only fallback after the new one (fact `raid-summary-tool-keys`; test_072 must stay green). Never send the old query again.
6. **F6, SPEC-004 + BUG-003 (sc-569 "works for Claude"):** the thinking throttle sets its slot before knowing whether a line comes out, and never sends a held-back line (`backend/app/agent_runner.py` ~529-545). Spend the slot only when a line is sent, and send the pending line on the next allowed tick or when the call ends (its final event or tool call), unless answer text has started. Keep SEC-003's bound (at most one clean-up per second) and the existing 080 tests' guarantees (adjust `test_the_status_clean_up_runs_at_most_once_a_second` only where it pinned the bug). Chat turns only.

## File footprint (board owner:* keys, to nils)
- `wcl_agent/agent.py`, `backend/app/services/profile_context.py`, `backend/app/agent_tools/mechanics.py`,
  `backend/app/services/raid_summary.py`, `backend/app/agent_runner.py`
- `backend/tests/test_080_thinking_runner.py`, `backend/tests/test_prompt_contract.py`, new `backend/tests/test_083_*.py`
GitNexus: `impact` before each edited symbol (`_run_turn` is CRITICAL: chat-only change, the USER_ID test must stay byte-identical); `detect-changes` once before hand-off.

## Live
Post `live-check:083` with the re-check steps: "The Ula'tek heart" in a fresh chat on Claude haiku (EXPECT: a `get_boss_mechanics` call returning found:true, Venomous Heart); one Claude multi-tool turn shows a thought line (not only "Thinking… Ns") in a gap. Team-lead runs it at the tip after the merge.

## Hand-off
Commit, `check.py run --as nils --base <the base above>` on the committed head, post a `handoff`, return about 15 lines: per fix the test that proves it, RESULT/RECEIPT, your `Retro:` line. No Shortcut moves (the stories are Under Review already).

## Known facts
- **raid-summary-tool-keys**: the Raids page recomputes the tools' exact store keys; a query-shape change empties that part; test_072 fails first.
- **wcl-time-window-args** (078): whole-report playerDetails is a startTime/endTime window; `fightIDs: null` fails on some reports.
- **runner-interim-retraction** (080): interim retraction rules; chat turns only.
- **stream-response-shared-by-jobs**: `_run_turn` also serves greeting, guide jobs, evals (USER_ID); output must stay identical.
- **profile-context-class-from-known-player** (082): the class fill and its 15-player window.
- **tool-docstring-is-prompt**: prompt text is pinned verbatim in several tests; test_064 caps instruction plus schemas.
- **mechanics-notes-per-tier** (081): notes are one JSON file per tier, loaded once.
