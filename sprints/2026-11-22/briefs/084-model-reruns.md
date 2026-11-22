# Brief 084: model re-runs and the runner (chat reliability)

- **Feature / branch:** 084, `084-model-reruns`. **Tier M** (one Spec Kit pass, no gates; answer your own clarify questions on the board as `scope:084:<topic>`).
- **Seat:** dev-4 (Vera). **Model/effort:** opus high (agent loop, retries, time budgets).
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached). **Base ref:** `sprint-2026-11-22` at 4fc12a3. Create your branch from it.
- **In parallel:** Edda (dev-5, 085 status frames and turn costs: ws.py + frontend), Ansel (dev-1, 086 mechanics notes and rankings). After you merge, a fresh dev-4 run takes 087 (Claude history cache) on model_retry.py and agent.py: leave the cache code (`_pin_time_block`, `_build_anthropic_kwargs` cache parts, `inject_preamble`) to it.
- **Security-core:** no. No migration.
- **Order:** sc-586 first (the owner's priority), then sc-580, then the runner items of sc-582.

## Stories and acceptance criteria (verbatim from the tickets)

**Gemini empty answers (sc-586, 2 pts).** Found in the 11-20 live pass (vertex, gemini-3.1-pro-preview): 2 of 7 turns ended with "I couldn't put an answer together". ADK events show finish STOP with an empty text part and 0 candidate tokens: once on the very first call (no tools, no thoughts, "is frost mage difficult?" in a fresh chat), once after one get_report_events call (2nd turn).
- A Gemini call that ends STOP with no text, no function call and 0 candidate tokens is re-run once before the empty-answer message; the re-run is recorded in turn stats.
- Check whether the rate changed with the 2026-11-20 prompt changes (082) before tuning anything else.
- Live: the frost question in a fresh chat answers on Gemini.

**Claude output budget and time (sc-580, 2 pts).**
- PERF (Medium): 079 raised the Claude chat output limit from 8,192 to 32,000 tokens (`wcl_agent/llm/model_retry.py` CLAUDE_MAX_TOKENS). A call that spends the whole budget on thinking now runs about 5-11 minutes (~$0.32) before the low-effort re-run, which also misses the history cache. Fix: cap thinking (effort) or a per-call time budget.
- SEC-001 (Low): the one budget re-run per call is not counted by the per-turn round cap, so each round can drive more output tokens than before.
- SPEC L2 (Low): `TurnStats.budget_retries` is counted but the `turn stats` INFO line (`backend/app/agent_runner.py` stream_response) doesn't show it.

**Thinking status edge cases (sc-582), your part: the runner items.**
- BUG-005: after 079's low-effort re-run, the status line can splice two calls' thoughts. (Your sc-586 re-run must not splice either.)
- BUG-006: retracted text isn't restored when a turn ends with a tool call still pending (no current trigger found).
- SPEC L1: a markdown heading counts as a sentence only when a blank line follows it (`_status_line`, agent_runner.py ~76-103).
- Residual of scope:080:retraction-guard: a short answer (<600 chars) followed by a gathering call and a non-empty closing line is still retracted.
The socket/UI items of sc-582 (BUG-004, SEC-002 residual, retry labels) are Edda's (085). Leave the `thinking`/`interim`/`model_retry`/`model_fallback` record shapes unchanged (see `contract:chat-status-records`).

## PO decisions already made
- `budget_retries` and a new `empty_retries` (name it so) go on the `turn stats` INFO line; no new metric instrument (the line is in Loki; posted as decision:sc-580-metrics).
- Every re-run (budget or empty STOP) counts as a round toward `round_cap`, and a call gets at most one re-run of either kind.
- Product bound on Claude call time: no single chat model call (thinking included) may run longer than **180 s** before it is cut off and handled like the thinking-only cut-off (one low-effort re-run, same bound). Pick the mechanism (effort cap, wall-clock deadline or both) after reading ADK; post it as `scope:084:claude-call-time`. A non-streamed call (CLI) keeps its 16k limit.

## File footprint (board `owner:` keys)
- `wcl_agent/llm/model_retry.py` (all but the cache layout code named above)
- `wcl_agent/agent.py`: only the thinking/planner config block (~lines 600-620)
- `backend/app/agent_runner.py`
- tests: new `backend/tests/test_084_*.py`; existing `test_079_claude_cache_budget.py`, `test_080_thinking_runner.py`, `test_model_retry.py`, `test_046_empty_turn.py`, `test_runner_retry.py`
- `specs/084-model-reruns/**`, `.claude/team/facts/` (facts you add or fix)
Anything else: `blocker` keyed `ask:<path>`.

## Bounds (test each at the bound before the path's first code)
- time: one Claude chat call ≤ 180 s incl. thinking; its one re-run under the same bound; the retry loop's wait budget (90 s) unchanged. Test with the `_clock` seam (fact clock-seam-wall-clock-budgets): a call that never ends is cut at the bound and the re-run is the only extra call.
- rate: ≤ 1 re-run per call (budget or empty STOP, not both); re-runs count in `round_cap`. Test: a fake that always returns empty STOP / thinking-only gets exactly one re-run, and a turn of N such calls trips the cap.
- held resources: a cut-off call's stream is closed (no task or connection left running); the turn lane is not held past the bound. Test asserts the cancelled call.
- growth: none expected; `empty_retries` is a counter.

## Live pre-check
If a question needs the real stack, post `live-check:084-pre` (kind `question`) with the exact command while you build; team-lead runs it at once. For sc-586 what makes the empty STOP likely: provider vertex, model gemini-3.1-pro-preview, a **fresh chat** whose first message is "is frost mage difficult?" (first call, no tools, no thoughts), and a 2nd turn after one get_report_events call; ask for ~6 fresh chats and the finish_reason/candidate tokens per call from the ADK events. For "did the rate change with 082": first try the read-only route, `obsq.py` over Loki for `turn stats ... outcome=empty` per model before/after the 11-20 082 merge; only if Loki has no history, ask team-lead in the pre-check.

## Read the installed library first
Read the installed ADK code for this path in the main checkout's `.venv/lib/python*/site-packages/google/adk/` (`models/google_llm.py` for how a streamed Gemini response ends and what an empty STOP looks like; `models/anthropic_llm.py` for effort, max_tokens and streaming) before designing.

## Known facts

Team facts for `wcl_agent/llm/model_retry.py`, `wcl_agent/agent.py`, `backend/app/agent_runner.py`, and the paths you run: `backend/tests/test_079_claude_cache_budget.py`, `backend/tests/test_080_thinking_runner.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **claude-prompt-cache-layout** (direct: sym:wcl_agent/llm/model_retry.py::_pin_time_block is in wcl_agent/llm/model_retry.py; verified 9ea3f72 2026-11-20): Claude chat requests cache three prefixes (079): tools, the instruction up to <CURRENT_TIME>, and the conversation's last block (RetryingClaude sets ADK's cache_config). The time block is split off and pinned per turn (TurnStats.pinned_time). Text that varies per request must go after the time block or into the turn's user message: anything changing earlier in the instruction, a model switch or an effort change voids the history cache for that call. Check usage cache_creation_input_tokens per call.
- **clock-seam-wall-clock-budgets** (direct: sym:wcl_agent/llm/model_retry.py::_clock is in wcl_agent/llm/model_retry.py; verified b9cf9a3 2026-11-05): A wall-clock budget reads a module-level `_clock = time.monotonic` that tests replace (`model_retry._clock`; the "sleeps" fixture in `test_model_fallback.py` advances it). Never patch `time.monotonic` globally: asyncio and the libraries read it too.
- **module-state-needs-reset** (direct: sym:wcl_agent/llm/model_retry.py::_limited_until is in wcl_agent/llm/model_retry.py; verified b9cf9a3 2026-11-05): Some state is process-wide module state and survives from one test to the next: the raw-store breaker (`raw_fetch_reads.breaker`), the report tombstones (`fetch_persistence._tombstones`) and the model retry memory (`model_retry._limited_until`). A test that trips them needs a reset. When `conftest.py` isn't yours, add an autouse fixture in your own test module, as `test_raw_store_probe.py` does.
- **runner-interim-retraction** (direct: sym:backend/app/agent_runner.py::_run_turn is in backend/app/agent_runner.py; verified 8986855 2026-11-20): On chat turns an 'interim' record means: all answer text streamed so far was progress; ws.py clears its tokens (after sending the frame), App clears streamRef. Only text <= INTERIM_MAX_CHARS, not next to a PRESENTING_TOOLS call, is retracted, never after text was kept; a turn ending without an answer re-emits the retracted text as a token. Answer = tokens after the last interim. Jobs (USER_ID) get none of this. 'thinking' needs event.author == runner.agent.name in fakes.
- **runner-outcome-flag-on-record** (direct: sym:backend/app/agent_runner.py::_run_turn is in backend/app/agent_runner.py; verified 8986855 2026-11-20): To tell `ws.py` about a turn's outcome, put a flag on the yielded record, never match on its text. The closing no-answer token carries `"empty": True`; `ws.py` pops it before sending (the wire frame is unchanged) and then skips the KB offer, the title and follow-up suggestions.
- **runner-test-fakes** (direct: file:backend/app/agent_runner.py; verified 8986855 2026-11-20): The `agent_runner` tests feed `SimpleNamespace` events and parts through fake runners (`test_046_empty_turn`, `test_tool_start_once`, `test_context_injection`, whose strict `run_async` takes only user_id, session_id, new_message and run_config). Read event fields with `getattr` and a default, and pass extra `run_async` kwargs only on the paths that need them (`state_delta` on chat turns only).
- **stream-response-shared-by-jobs** (direct: sym:backend/app/agent_runner.py::stream_response is in backend/app/agent_runner.py; verified 8986855 2026-11-20): `stream_response` and `_run_turn` serve chat turns AND greeting, guide jobs and evals. Those jobs run as `USER_ID` (`"local_user"`). Chat-only behaviour keys on `user_id != USER_ID`, for example the no-answer token, the `app_turns` state_delta and the `thinking`/`interim` records (080). GitNexus rates both CRITICAL.
- **tool-docstring-is-prompt** (direct: sym:wcl_agent/agent.py::drop_schema_titles is in wcl_agent/agent.py; verified 8986855 2026-11-20): A tool's whole docstring is its model-facing description, sent every request. Keep usage rules in one place (docstring or instruction); leave result shapes out. ADK adds no per-parameter descriptions; agent.drop_schema_titles strips pydantic titles. test_064_prompt_budget caps instruction plus schemas at 12,733 chars/4 per provider. Prompt text is pinned verbatim, some pins across line breaks, in backend/tests/test_{prompt_contract, 046_compact_tables, 046_search_data, 050_report_fights (also a docstring), 050_kickoff_overview, kb_search_prompt, kb_eval, profile_tools, 082_coach_defaults, 083_sprint_fixes}.py; test_capabilities requires every tool to have a docstring.
- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_079_claude_cache_budget.py (you run it); verified 8986855 2026-11-20): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **wcl-agent-no-backend-imports** (file: file:wcl_agent/ contains wcl_agent/llm/model_retry.py; verified 8986855 2026-11-20): `wcl_agent` never imports `backend`: it runs standalone, and only backend may import wcl_agent. So OTel instruments for wcl_agent code live in wcl_agent (`app.cache.requests` in `cache.py`, the GenAI spans in `generation.py`; OTel API only, no-ops without a provider), and shared helpers move into wcl_agent (`neutralise` in report_tools, `DIFFICULTY_NAMES` in `wcl_agent/game`).
- **metric-attributes-allowlist** (neighbour: file:backend/app/telemetry/metrics.py called by backend/app/agent_runner.py::_record_ttft; verified 32010a6 2026-11-05): A backend metric label survives only if its key is in `setup.METRIC_ATTRIBUTES`: one global allowlist, applied through a View to every instrument, library ones included. New app attributes are enums namespaced `app.*` (`app.cache.name`, `app.rag.index`), because a bare key like `result` would let any library's attribute of that name through. `session.id` is never a metric label.
- **otel-env-strip-in-tests** (neighbour: file:backend/tests/conftest.py calls wcl_agent/llm/model_retry.py::forget_rate_limits; verified b9cf9a3 2026-11-05): Backend telemetry switches on from `OTEL_EXPORTER_OTLP_ENDPOINT` alone, and the standard `OTEL_*` names reach every child process of a shell that set them (`bin/claude-otel` exports them for Claude Code). `backend/tests/conftest.py` deletes every `OTEL_*` at import. A new script or tool that starts the backend outside pytest must clear them too, or it exports into someone else's stack.

(2 more: `facts.py brief --all ...`)
