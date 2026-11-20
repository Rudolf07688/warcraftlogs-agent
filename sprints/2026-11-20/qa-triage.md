# QA triage, sprint 2026-11-20 (PO Maren)

Inputs: QA sweep on d7dab27...f07ffb7 (`qa-reports/2026-11-20/README.md`: spec 0/1/3/5, bugs 0/0/2/4, perf 0/0/2/4,
security 0/0/0/1), the D18 review of 080 (fixed in its rework), and team-lead's live passes 1 and 2 (#109, #111).
Fix bar: a broken AC, a security hole or data loss, Medium and above in new code; Lows only inside a hunk being fixed.

## Fix round (one fresh developer, brief 083-sprint-fixes)
| # | Finding | Why it meets the bar | File |
|---|---|---|---|
| F1 | "The Ula'tek heart" skips get_boss_mechanics (SPEC-001 High; live 2/2 FAIL on haiku) | sc-571 AC (owner's two questions) broken; caused by 082's example | wcl_agent/agent.py |
| F2 | 082 deleted the PERSONALITY rule "Settle the facts…" (SPEC-002) and "or unrelated" (L5, same prompt hunk) | out-of-scope removal of contracted prompt text | wcl_agent/agent.py |
| F3 | Class fill compares realms as text, not slug (BUG-001) | sc-575 AC (stored class read before asking) still fails for "Tarren Mill" vs "tarren-mill" | backend/app/services/profile_context.py |
| F4 | Encounter with a difficulty suffix misses an existing note (BUG-002, spot-checked) | sc-571 AC: a real mechanic answered "not in my guides" | backend/app/agent_tools/mechanics.py |
| F5 | Raids page no longer finds pre-078 whole-report participant rows (SPEC-003) | regression (stored data no longer shown) from 078 | backend/app/services/raid_summary.py |
| F6 | Thinking throttle spends its slot on chunks that emit nothing and never flushes a held line (SPEC-004 + BUG-003) | sc-569 AC "works for Claude" partially broken by the SEC-003 rework | backend/app/agent_runner.py |

## Deferred (backlog, label qa-deferred, grouped by root cause)
- Claude output budget and time (perf Medium: a thinking-only 32k call can run 5–11 min; security SEC-001 Low: the budget re-run is outside the round cap; spec L2: budget_retries not in the turn-stats line).
- Cross-turn Claude history cache (perf Medium; Vera's backlog:claude-cross-turn-cache).
- Status/interim edges in 080 (BUG-004, BUG-005, BUG-006, spec L1 heading-as-sentence, the #102 short-answer residual, D18 SEC-002 lost-frame residual; Edda's backlog:status-under-cards-retry).
- Small perf (082b settings read selects the whole row; status line in App state re-renders; damage_fields note per result; mechanics schema tokens).
- Hardening (cached prompt head must hold no tenant data: add a test; lint for mechanic notes).
- Mechanic notes coverage (Ansel's backlog:mechanics-coverage: Nymrissa, Kith'ix re-source; spec L3 boss name inside the ability text).
- Empty Gemini turns: finish STOP with no text and 0 candidate tokens, 2 of 7 live turns (pre-existing path; Gemini twin of sc-567).
- Whole-report rankings still send fightIDs: null (spec, outside the diff; check whether it fails like playerDetails).
- Spec L4 (080 tasks.md T013/T014 unchecked): doc drift, no ticket; fixed in the close-out if touched.
