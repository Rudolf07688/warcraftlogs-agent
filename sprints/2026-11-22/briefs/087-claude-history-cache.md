# Brief 087: Claude history cache across turns

- **Feature / branch:** 087, `087-claude-history-cache`. **Tier M** (one Spec Kit pass, no gates; answer your own clarify questions as `scope:087:<topic>`).
- **Seat:** dev-4 (Vera), a fresh run after 084. **Model/effort:** opus high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a`. **Base ref:** the `sprint-2026-11-22` tip after 084 merged (given in the launch prompt).
- **In parallel:** whoever is still running from 085 (Edda, ws.py + frontend) and 086 (Ansel, mechanics/report tools).
- **Security-core: yes** (the shared prompt-cache head; tenant data must never sit in it). The PO runs a qa-security review at hand-off. No migration.

## Stories and acceptance criteria (verbatim from the tickets)

**Claude history cache (sc-581, 3 pts).** 079 caches within a turn (input cost -47% fresh, -75% repeat, measured live) and the tools+instruction head across turns. But each turn's first Claude call rewrites the whole history cache at 1.25x instead of reading it at 0.1x: the per-turn time block (system, `wcl_agent/agent.py` build_instruction, pinned per turn by `_pin_time_block` in model_retry.py) and the per-turn preamble on the previous turn's user message (`inject_preamble`) both sit before the history.
Fix idea: move both after the history (a text block after the last tool_result with earlier copies kept, or a clear-at system message). Needs agent.py; measure the gain first (older turns' tool results are already stubbed).

**Cache and notes hardening (sc-584), your part: the cached head.**
- 079 caches the tools + instruction head at a shared breakpoint. Today it holds no tenant data, but nothing enforces it: add a test that the cached part of an Anthropic request never contains the KNOWN PLAYER CONTEXT preamble or any workspace data.
(The notes lint is Ansel's, 086.)

## Hazards to design around
- The time block changes every minute; anything that varies per turn before a breakpoint voids everything after it (fact claude-prompt-cache-layout). Measure first: `tokens.py` and fake-request byte comparisons of turn N's history prefix against turn N+1's; post the expected saving before building.
- Keeping earlier copies of the preamble in history makes every request grow by one preamble per turn: bound it (see Bounds).
- Replayed thinking blocks are dropped on prefix mismatch (`drop_block`); a layout change must not make every turn drop them.
- Gemini shares `inject_preamble` and the instruction: its behaviour must not change (implicit caching only).
- The cached head is shared across tenants: two tenants' requests must produce a byte-identical head up to the shared breakpoint.

## File footprint (board `owner:` keys, posted at launch)
- `wcl_agent/llm/model_retry.py` (cache layout: `_pin_time_block`, `_build_anthropic_kwargs`, `inject_preamble`, the before-model callback's preamble step)
- `wcl_agent/agent.py` (`build_instruction` and the time block)
- `wcl_agent/llm/context_trim.py` only if the layout needs it
- tests: new `backend/tests/test_087_*.py`; existing `test_079_claude_cache_budget.py`, `test_context_injection.py`, `test_prompt_contract.py`, `test_064_prompt_budget.py` (ask if 086 still holds it)
- `specs/087-claude-history-cache/**`, `.claude/team/facts/`

## Hostile inputs (one test each, before the code; assert on the built request: what sits before each cache breakpoint)
- a player, guild or report name in the preamble containing `<CURRENT_TIME>`, `</CURRENT_TIME>` or `@@CURRENT_TIME@@`: the split still happens at the instruction's own marker, never inside tenant text
- a user message containing those markers
- KNOWN PLAYER CONTEXT, coaching briefs, profile names, tracked raids: never at or before the shared tools+instruction breakpoint
- two tenants with different preambles: identical bytes up to the shared breakpoint
- a model switch (021 fallback) and an effort change (084's re-run) mid-turn: no tenant data moves into the head
- a forged `cache_control` or system-looking text inside user content: not treated as a breakpoint or instruction

## Bounds
- growth: prompt growth from kept per-turn blocks is capped (e.g. only the latest preamble in full, older ones stubbed or dropped): test a 30-turn conversation stays under the prompt budget
- size: the per-turn block after the history is the existing preamble cap; test at the cap
- time/held resources: none new (no extra calls)

## Live pre-check
If a question needs the real stack, post `live-check:087-pre` (kind `question`) with the exact command while you build; team-lead runs it at once. Expected live proof at the tip: on a 3-turn Claude chat, turn 2's and turn 3's first calls read the history from the cache (`cache_read_input_tokens` covers the prior turns, `cache_creation` only the new turn).

## Read the installed library first
Read the installed ADK code in the main checkout's `.venv/lib/python*/site-packages/google/adk/models/anthropic_llm.py` (where ADK places cache breakpoints and how it builds system and messages) before designing.

## Known facts
(regenerated at launch)
