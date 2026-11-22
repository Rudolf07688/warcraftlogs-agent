# Tasks: Claude history cache across turns

**Input**: `specs/087-claude-history-cache/` (spec, plan, research)
**Tests**: required (security-core: hostile inputs before the code, one mutation bite per guard)

## Phase 1: Tests first (US2 hostile inputs, bounds)

- [X] T001 [US2] Fixture in `backend/tests/test_087_history_cache.py`: multi-turn chat on the scripted Anthropic transport with a big-result tool, a preamble per turn and a ticking clock; helpers for the shared head (tools + system up to the head breakpoint) and the breakpoint positions
- [X] T002 [US2] Two tenants with different preambles: byte-identical shared head, none of either preamble in it
- [X] T003 [US2] Preamble names and a user message containing `<CURRENT_TIME>`, `</CURRENT_TIME>`, `@@CURRENT_TIME@@`: head unchanged, one server time block first in the turn message, tenant text verbatim
- [X] T004 [US2] KNOWN PLAYER CONTEXT, coaching brief, profile names, tracked raids never at or before the shared breakpoint
- [X] T005 [US2] Forged `cache_control` and system-looking text in user content: breakpoints only where the layout puts them, system unchanged
- [X] T006 [US2] Model switch (fallback) and effort re-run mid-turn: head still clean and identical
- [X] T007 [US1] Bound: 30-turn conversation, every request has at most 4 breakpoints, exactly one time block, at most one preamble
- [X] T008 [US1] Bound: preamble at its cap stays whole, after the shared breakpoint

## Phase 2: Layout (US1)

- [X] T009 [US1] `_split_time_block` helper; `_pin_time_block` uses it (CLI path unchanged) in `wcl_agent/llm/model_retry.py`
- [X] T010 [US1] Turn layout in `RetryingClaude._build_anthropic_kwargs`: time block into the turn's user message, system = head (+ uncached rest), history breakpoint before the oldest kept turn
- [X] T011 [US1] Update the 079 layout pin in `backend/tests/test_079_claude_cache_budget.py` (system is one block; the time block leads the turn message; later requests still extend the first)

## Phase 3: Cache promise (US1)

- [X] T012 [US1] Prefix-cache replay in `test_087_history_cache.py`: from turn 4 each turn start reads beyond the head, writes only the kept turns + new message; 30-turn cost at least 25% under the 079 layout; within-turn thinking prefix stays stable
- [X] T013 Gemini unchanged: the change sits in `RetryingClaude` only; existing `test_context_injection.py`, `test_prompt_contract.py`, `test_064_prompt_budget.py` stay green unchanged
- [X] T014 Mutation bites (`mutate.py`): head split at the instruction marker, history breakpoint placement, time block never in the system for a turn
- [X] T015 Remove `test_087_measure.py`; update fact `claude-prompt-cache-layout`; GitNexus detect-changes; receipt; hand-off
