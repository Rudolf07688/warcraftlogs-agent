# Sprint 2026-11-22 plan: chat reliability

Steer (owner, board #1): the eight deferred QA follow-ups from sprint 2026-11-20, 17 pts.
Branch `sprint-2026-11-22`, base 4fc12a3. Iteration `2026-11-22` (598). No migration.

Goal: chat turns answer on both providers, never sit for minutes on a thinking-only call,
and cost less per turn; the cached prompt head provably holds no tenant data.

## Stories (ticket text, copied once)

| Ticket | Pts | What it asks |
|---|---|---|
| Gemini empty answers (sc-586) | 2 | STOP + no text + no call + 0 candidate tokens is re-run once before the no-answer message, recorded in turn stats; check whether the rate changed with 082's prompt changes before tuning; live: the frost question in a fresh chat answers on Gemini. |
| Claude output budget and time (sc-580) | 2 | A thinking-only 32k call runs 5-11 min: cap thinking (effort) or a per-call time budget; the budget re-run counts in the round cap; `budget_retries` on the turn-stats line (and metrics). |
| Claude history cache (sc-581) | 3 | Each turn's first Claude call rewrites the history cache: the per-turn time block and the preamble sit before the history. Move them after it; measure the gain first. |
| Thinking status edge cases (sc-582) | 3 | BUG-004 cancel from a 2nd tab during the interim send keeps retracted text in the saved partial; BUG-005 status line splices two calls' thoughts after a re-run; BUG-006 retracted text not restored when a turn ends with a tool call pending; SPEC L1 heading counts as a sentence only with a blank line after; short answer (<600) + gathering call + closing line is still retracted; SEC-002 residual: a lost interim frame leaves retracted text local-only; retry/fallback labels never show once spell cards exist. |
| Small chat-turn costs (sc-583) | 2 | Preamble reads the whole settings row + a dropped onboarding query (select main_class/main_spec only); thinking status lives in App state (move to a small store); damage_fields note (~120 tokens) per result (once per turn or shorter); get_boss_mechanics schema ~183 tokens (trim if the budget tightens). |
| Cache and notes hardening (sc-584) | 2 | Test: the cached part of an Anthropic request never holds the KNOWN PLAYER CONTEXT preamble or workspace data. Lint the mechanic notes: source URLs on allowed hosts, no markup, no instruction-like text. |
| Boss-mechanic notes (sc-585) | 2 | Notes for Nymrissa Wavecaller (zone 53, encounter 3379); re-source Kith'ix (Method guide if one exists now); `get_boss_mechanics("nekzali gravebound")` (boss name inside the ability text) finds the ability. |
| Whole-report rankings (sc-587) | 1 | Reproduce `rankings(fightIDs: null)` on the three Veritass reports via a live pre-check; fix like the player list (keeping Raids page keys in step) only if it fails. |

## Features (one developer run each)

| Feature | Stories | Tier | Seat / model | Footprint core |
|---|---|---|---|---|
| 084 model re-runs and the runner | 586, 580, 582 runner items (BUG-005, BUG-006, L1, short-answer residual) | M | dev-4 Vera, opus high | model_retry.py, agent.py (thinking config), agent_runner.py |
| 085 status frames and turn costs | 582 socket/UI items (BUG-004, SEC-002 residual, retry labels), 583 settings read + status store | M, security-core | dev-5 Edda, opus high | ws.py, repository.py (one narrow read), frontend/src/** |
| 086 mechanics notes and rankings | 585, 587, 584 notes lint, 583 damage_fields note + mechanics schema | S | dev-1 Ansel, opus medium | kb/mechanics/**, agent_tools/mechanics.py, report_tools.py, raid_summary.py |
| 087 Claude history cache | 581, 584 cached-head test | M, security-core | dev-4 Vera (fresh), opus high | model_retry.py (cache), agent.py (instruction) |

Order: 084, 085, 086 start at once. 087 starts after 084 merges (same files).

## Decisions
- Split by file, not by ticket: 582, 583 and 584 each span two streams; PO owns their states.
- 084 owns agent_runner.py and model_retry.py; 087 follows it on model_retry.py/agent.py.
- 086 is tier S despite ~5 pts: three small independent fixes with explicit ACs, no data model.
- sc-580 metrics: the turn-stats line (Loki) carries the counters; no new metric instrument.
- No scrum master: no file is shared in the same window.

## Risks / drop first
- 087 depends on 084: the long pole. Drop first: 583 mechanics schema trim, then 584 lint scope.
- Gemini empty STOP may not reproduce on demand: the AC holds by fake test; live is best-effort.
