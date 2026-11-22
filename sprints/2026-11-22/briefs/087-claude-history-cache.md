# Brief 087: Claude history cache across turns

- **Feature / branch:** 087, `087-claude-history-cache`. **Tier M** (one Spec Kit pass, no gates; answer your own clarify questions as `scope:087:<topic>`).
- **Seat:** dev-4 (Vera), a fresh run after 084. **Model/effort:** opus high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a`. **Base ref:** `sprint-2026-11-22` at 64c9413 (084 and 086 merged). Note from 084: `RetryingClaude.generate_content_async` now splits request()/call(); 084 added the 180 s bound and re-runs (fact model-call-one-rerun). An effort change on a re-run voids the history cache for that call: that is accepted.
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
- tests: new `backend/tests/test_087_*.py`; existing `test_079_claude_cache_budget.py`, `test_context_injection.py`, `test_prompt_contract.py`, `test_064_prompt_budget.py`
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
Team facts for `wcl_agent/llm/model_retry.py`, `wcl_agent/agent.py`, `wcl_agent/llm/context_trim.py`, and the paths you run: `backend/tests/test_079_claude_cache_budget.py`, `backend/tests/test_context_injection.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **claude-prompt-cache-layout** (direct: sym:wcl_agent/llm/model_retry.py::_pin_time_block is in wcl_agent/llm/model_retry.py; verified 9ea3f72 2026-11-20): Claude chat requests cache three prefixes (079): tools, the instruction up to <CURRENT_TIME>, and the conversation's last block (RetryingClaude sets ADK's cache_config). The time block is split off and pinned per turn (TurnStats.pinned_time). Text that varies per request must go after the time block or into the turn's user message: anything changing earlier in the instruction, a model switch or an effort change voids the history cache for that call. Check usage cache_creation_input_tokens per call.
- **clock-seam-wall-clock-budgets** (direct: sym:wcl_agent/llm/model_retry.py::_clock is in wcl_agent/llm/model_retry.py; verified b9cf9a3 2026-11-05): A wall-clock budget reads a module-level `_clock = time.monotonic` that tests replace (`model_retry._clock`; the "sleeps" fixture in `test_model_fallback.py` advances it). Never patch `time.monotonic` globally: asyncio and the libraries read it too.
- **model-call-one-rerun** **STALE** (direct: sym:wcl_agent/llm/model_retry.py::_watch is in wcl_agent/llm/model_retry.py; verified 4fc12a3 2026-11-22): A model call gets at most one re-run (Gemini empty STOP, Claude thinking-only max_tokens, Claude streamed request past CLAUDE_CALL_TIMEOUT_S): the wrappers hold back the bad final via _watch and call again. _count_rerun bumps model_requests, so a re-run is a round toward round_cap. The runner resets a call's thought text when TurnStats.reruns changes: there is no final event between a held-back call and its re-run. Bound tests patch CLAUDE_CALL_TIMEOUT_S or _clock.
- **module-state-needs-reset** (direct: sym:wcl_agent/llm/model_retry.py::_limited_until is in wcl_agent/llm/model_retry.py; verified b9cf9a3 2026-11-05): Some state is process-wide module state and survives from one test to the next: the raw-store breaker (`raw_fetch_reads.breaker`), the report tombstones (`fetch_persistence._tombstones`) and the model retry memory (`model_retry._limited_until`). A test that trips them needs a reset. When `conftest.py` isn't yours, add an autouse fixture in your own test module, as `test_raw_store_probe.py` does.
- **runner-test-fakes** **STALE** (direct: file:backend/tests/test_context_injection.py (you run it); verified 8986855 2026-11-20): The `agent_runner` tests feed `SimpleNamespace` events and parts through fake runners (`test_046_empty_turn`, `test_tool_start_once`, `test_context_injection`, whose strict `run_async` takes only user_id, session_id, new_message and run_config). Read event fields with `getattr` and a default, and pass extra `run_async` kwargs only on the paths that need them (`state_delta` on chat turns only).
- **tool-docstring-is-prompt** **STALE** (direct: sym:wcl_agent/agent.py::drop_schema_titles is in wcl_agent/agent.py; verified 8986855 2026-11-20): A tool's whole docstring is its model-facing description, sent every request. Keep usage rules in one place (docstring or instruction); leave result shapes out. ADK adds no per-parameter descriptions; agent.drop_schema_titles strips pydantic titles. test_064_prompt_budget caps instruction plus schemas at 12,733 chars/4 per provider. Prompt text is pinned verbatim, some pins across line breaks, in backend/tests/test_{prompt_contract, 046_compact_tables, 046_search_data, 050_report_fights (also a docstring), 050_kickoff_overview, kb_search_prompt, kb_eval, profile_tools, 082_coach_defaults, 083_sprint_fixes}.py; test_capabilities requires every tool to have a docstring.
- **pg-tests-shared-db** **STALE** (file: file:backend/tests/ contains backend/tests/test_079_claude_cache_budget.py (you run it); verified 8986855 2026-11-20): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **wcl-agent-no-backend-imports** **STALE** (file: file:wcl_agent/ contains wcl_agent/llm/model_retry.py; verified 8986855 2026-11-20): `wcl_agent` never imports `backend`: it runs standalone, and only backend may import wcl_agent. So OTel instruments for wcl_agent code live in wcl_agent (`app.cache.requests` in `cache.py`, the GenAI spans in `generation.py`; OTel API only, no-ops without a provider), and shared helpers move into wcl_agent (`neutralise` in report_tools, `DIFFICULTY_NAMES` in `wcl_agent/game`).
- **otel-env-strip-in-tests** (neighbour: file:backend/tests/conftest.py calls wcl_agent/llm/model_retry.py::forget_rate_limits; verified b9cf9a3 2026-11-05): Backend telemetry switches on from `OTEL_EXPORTER_OTLP_ENDPOINT` alone, and the standard `OTEL_*` names reach every child process of a shell that set them (`bin/claude-otel` exports them for Claude Code). `backend/tests/conftest.py` deletes every `OTEL_*` at import. A new script or tool that starts the backend outside pytest must clear them too, or it exports into someone else's stack.
