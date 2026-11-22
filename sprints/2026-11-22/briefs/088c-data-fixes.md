# Brief 088c: Raids page rankings key, mechanic miss wording, cohort server match (fix round)

- **Branch:** `088c-data-fixes`. **Seat:** dev-1 (Ansel), fresh run. **Model:** opus medium. **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c`.
- **In parallel:** Vera (088a), Edda (088b). Not security-core; the Raids page read stays tenant-scoped.
- **Tier S** (short plan, then implement; no Spec Kit). Fix round: fix the listed findings and nothing else (owner rule: no scope creep); anything more is a `backlog:<topic>` notice.
- **Base ref:** `sprint-2026-11-22` at 39c4b3f (all four streams merged, full suite green at f1835c4). Create your branch from it and use it as `--base`.
- **Reports** (read the cited sections, they hold file:line and the failure path): /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-22/bugs.md (BUG-002), /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-22/security.md (SEC-002), board entry 91 (live F1, F2)
- One test per finding that fails before the fix; a mutation bite for any guard; `check.py run --as <you> --base 39c4b3f` on the committed head; hand-off on the board and a short result (RESULT/RECEIPT lines, one line per finding with its test).
- **Live pre-check:** if a question needs the real stack, post `live-check:088-pre` (kind `question`) with the exact command; team-lead runs it at once.

## Findings to fix
1. **BUG-002 (Medium)** `raid_summary.py` ~157/~433 with `report_tools.py` ~928: get_report_rankings stores its row under a key with the explicit fightIDs list from the summary at call time; the Raids page rebuilds the key from the newest stored summary. For a report still being logged the lists differ and the parses vanish. Make the Raids page find the newest whole-report rankings row for the report regardless of the fight list (or store under a stable logical key while sending the explicit list): your call, `scope:088c:rankings-key`; keep the fact raid-summary-tool-keys true.
2. **Live F1 (Gemini FAIL)**: "What does Gravebound do on Nekzali?": the tool answers found:false for Nek'zali with found_under [The Coiled Altar], then the Coiled Altar note, but neither model tells the user it is not a Nek'zali mechanic. Make the miss say it outright, e.g. "Gravebound is not a Nek'zali the Soulcoiler mechanic in my guides; it is The Coiled Altar's. Tell the user which boss it belongs to." (and/or the found answer carries the asked boss and the boss it belongs to). Keep the docstring routing (test_083 F1) and the prompt budget.
3. **Live F2 (pre-existing, taken in: decision:f2-cohort-server)** `wcl_agent/tools/benchmark.py` ~385: compare_player_to_cohort with {report_code tbjGm2MkAd8KxwLN, fight_id 4, source_id 88, player_name Traecie} errors "'Traecie' has no ranking row for fight 4 (metric dps)" while ranked_players lists Traecie: the name matches and the server comparison (resolved.server vs r.server) rejects the row. Likely display name vs slug (083 F3 fixed the same class of bug in the class fill by comparing realm slugs). Compare by normalised slug; test with a fixture whose two sides spell the realm differently.
4. In-hunk Low **SEC-002**: note prose fields may carry plain URLs to any host (`mechanics.py` ~35/~45): reject URLs in prose fields in the notes lint.

## Footprint
`backend/app/services/raid_summary.py`, `wcl_agent/tools/report_tools.py`, `backend/app/agent_tools/mechanics.py`, `backend/app/kb/mechanics/**`, `wcl_agent/tools/benchmark.py`, new `backend/tests/test_088c_*.py`, existing `test_072_raid_summary.py`, `test_086_mechanics_notes.py`, `test_081_boss_mechanics.py`, `test_report_rankings.py`, `test_benchmark.py`, `.claude/team/facts/`.

## Hostile inputs (notes lint, SEC-002)
- `https://evil.example/x`, `www.evil.example`, `evil.example/path`, `hxxp://` in a tip or summary field: rejected.

## Bounds
- size: the Raids page reads at most one rankings row per report (the newest), no scan over all rows of other reports.
