# Implementation Plan: Boss mechanics for the coach

**Branch**: `081-boss-mechanics` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

## Summary

Curated mechanic notes for the current raid tier in one JSON file per tier under `backend/app/kb/mechanics/`,
validated with Pydantic and loaded once at import; a lookup tool `get_boss_mechanics(ability, encounter=None)` in
`backend/app/agent_tools/mechanics.py`, added to the existing `KB_TOOLS` ("Stored knowledge") group, so
`agent_runner.py` registers it on every provider without a change (board decision:571-design).

## Technical Context

Python 3.14, Pydantic v2, google-adk FunctionTool; pytest. No storage beyond the JSON file, no migration, no new
dependency. Prompt budget share +400 tokens (contract:prompt-budget); measured +183 (gemini 11,763).

## Constitution Check

- I Reuse: the tool group and capability summary are reused; no copied lists (ids and names live only in the JSON).
- III Simplicity: exact/alias lookup over a few dozen notes; no vector index (decision:571-design).
- IV Typed contracts: the notes are validated Pydantic models; the tool returns the contracted dict shape.
- V Async: the tool is `async def` and does no I/O at call time (notes loaded at import).
- VI GitNexus: `KB_TOOLS` impact UNKNOWN, confirmed by text search: agent_runner.py and three tests read it; only
  test_kb_search.py pins the tuple (granted, #70).

## Design

- **Normalisation** (`normalise`): NFKC, casefold, all apostrophe styles to none, possessive "'s" dropped,
  non-word characters (punctuation, controls) as word breaks, a leading "the" dropped.
- **Index** at import: boss key -> encounter; ability key (name, aliases, ids) -> [(encounter, note)].
- **Lookup**: exact key; else, when a boss's name is inside the text ("ula'tek heart"), that boss's notes matching
  the rest. A named boss restricts hits to it; an ability found elsewhere is a miss with `found_under`
  (canonical names). Same key on two bosses with none named: a miss listing both.
- **Guards**: argument length <= 100 and non-empty (else a fixed error), nothing echoed, no file opened at call time.

## Files

- `backend/app/kb/mechanics/venomous_abyss.json` (new): 9 encounters, 92 notes.
- `backend/app/agent_tools/mechanics.py` (new): models, loader, normaliser, tool.
- `backend/app/agent_tools/kb_tools.py`: `KB_TOOLS` gains `get_boss_mechanics`.
- `backend/tests/test_081_boss_mechanics.py` (new); `backend/tests/test_kb_search.py` (one pin, granted).

## Complexity Tracking

None.
