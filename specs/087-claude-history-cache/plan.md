# Implementation Plan: Claude history cache across turns

**Branch**: `087-claude-history-cache` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/087-claude-history-cache/spec.md`

## Summary

Each chat turn's first Claude request rewrote the whole conversation cache because the per-turn
time block sat in the system, in front of the history, and because the trim boundary moves one
turn every turn. Measured offline (`research.md`): moving the time block alone gains nothing;
moving it into the turn's user message **and** adding a fourth cache breakpoint at the end of the
stubbed history makes every turn start read the stubbed history (-35% input cost over 30 turns).
Both changes live in `RetryingClaude._build_anthropic_kwargs`, after ADK places its three
breakpoints, so Gemini and the preamble injection are untouched. A test module pins that the
shared head holds no tenant data under hostile inputs, and replays a conversation through a
prefix-cache simulator for the cache promise.

## Technical Context

**Language/Version**: Python 3.14 (uv)
**Primary Dependencies**: google-adk (`anthropic_llm.Claude`), anthropic SDK
**Storage**: none (request layout only; no migration)
**Testing**: pytest, scripted Anthropic transport (`test_llm_provider_agent` fixtures)
**Target Platform**: backend chat runner (Linux container)
**Project Type**: web service (backend + `wcl_agent` library)
**Performance Goals**: SC-001: -25% or better input cost over a 30-turn replay
**Constraints**: max 4 cache breakpoints per request; provider look-back 20 blocks; 5-minute cache life
**Scale/Scope**: one function pair in `wcl_agent/llm/model_retry.py`

## Constitution Check

- I Reuse-first: reuses ADK's breakpoint placement and `context_trim.keep_turns()`; one split helper shared by the CLI path and the turn path. PASS
- II Step-wise: tests first (hostile inputs, bounds), then the layout, then the replay. PASS
- III Simplicity: no state, no preamble copies, no trim change (the alternatives measured worse). PASS
- IV Typed contracts: the request is the SDK's plain-dict params, as ADK builds them; no new boundary. PASS
- V Async: no new I/O, no extra calls. PASS
- VI GitNexus: `_pin_time_block` LOW; `_build_anthropic_kwargs` UNKNOWN (called by ADK on every Claude request) treated as HIGH; `inject_preamble` CRITICAL, so it is not touched. PASS
- VII shadcn: no UI. N/A
- VIII Backlog: sc-581 / sc-584 In Progress, Under Review at hand-off. PASS

## Project Structure

### Documentation (this feature)

```text
specs/087-claude-history-cache/
├── spec.md
├── plan.md
├── research.md      # measure:087 table and the rejected layouts
├── quickstart.md    # how to re-run the replay
├── checkpoint.md
└── tasks.md
```

### Source Code (repository root)

```text
wcl_agent/llm/model_retry.py          # _split_time_block, _pin_time_block, _turn_layout,
                                      # RetryingClaude._build_anthropic_kwargs
backend/tests/test_087_history_cache.py   # hostile inputs, bounds, cache replay
backend/tests/test_079_claude_cache_budget.py  # the 079 layout pin, updated to the new layout
```

**Structure Decision**: one module change; `wcl_agent/agent.py` and `context_trim.py` stay
unchanged (the instruction text is the same; only where Claude's request carries the time moves).

## Design

`_build_anthropic_kwargs(llm_request, ...)` for a request with a turn installed (`current_turn`):

1. ADK builds the request with breakpoints on the last tool, the system and the last message block.
2. `_split_time_block(system)` returns (head block, time block, rest) by `rpartition` on the
   instruction's own `<CURRENT_TIME>` (the system holds no tenant text). The time block is pinned
   per turn in `TurnStats.pinned_time` (079).
3. System becomes `[head]` plus `rest` as an uncached block when non-blank (ADK's static agent-identity line, and the round-cap wrap-up when present).
4. The turn's user message (last user message with a text block and no `tool_result`) gets the
   pinned time block as a new first text block.
5. With more than `keep_turns()` user turns, the last non-thinking block before the oldest kept
   turn's user message gets the same `cache_control` ADK used.

Without a turn (CLI) step 2-5 fall back to today's `_pin_time_block` split.

## Complexity Tracking

None.
