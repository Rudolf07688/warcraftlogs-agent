# Brief 079-claude-cache-budget (dev-4 Vera)

- **Feature / branch:** 079 / `079-claude-cache-budget`
- **Tier:** S x2, in sequence in this one run: sc-568 (caching) then sc-567 (output budget). No Spec Kit.
- **Model / effort:** opus, high
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at the base). **Base ref:** `d7dab27`.
- **Seat:** dev-4 (Vera). In parallel: Tomas (078, WCL tools), Edda (080, status line, owns `agent_runner.py` and `ws.py`), Ansel (081, boss mechanics), Nils (082, owns `wcl_agent/agent.py`).
- **Security-core:** no. **Migration:** none.
- Load the `claude-api` skill before designing: caching breakpoints, `max_tokens`, adaptive thinking, effort and thinking display are all there. Don't answer them from memory.

## Stories (acceptance criteria verbatim)

### sc-568 (3 pts, bug): No prompt caching on the Anthropic chat path: every model call re-reads ~60–69k prompt tokens
Trace 1d8086d1d78f29a1a0d46feab0d0b1e7 (claude-sonnet-5-5, Anthropic API): 7 calls with 59–69k input tokens each, every one `cache_read.input_tokens=0`, `cache_creation.input_tokens=0`; turn stats `cached_tokens=0`. Model time 142.6 s of the 145 s turn.
AC:
- The Anthropic chat requests carry cache breakpoints (system prompt + tools, and the growing history), so the second and later calls in a turn read most of the prompt from cache. Check how ADK's Anthropic adapter builds the request (model_retry.py already rewrites requests for the thinking beta).
- Turn stats and the gen_ai spans show `cache_read` > 0 from the second call on.
- Measure before and after on the same prompt: time to first token per call and turn cost.
- Gemini path unchanged.

### sc-567 (2 pts, bug): Claude chat turns end with "no answer" when thinking uses the whole 8,192-token output budget
Same trace: the last call took 67.6 s and stopped with `finish_reason=max_tokens`, `output_tokens=8192`, `reasoning.output_tokens=8192`: adaptive thinking (agent.py BuiltInPlanner, `thinking_budget=-1` for Anthropic) used the whole output budget. 8192 looks like ADK's Anthropic adapter default `max_tokens`.
AC:
- A Claude chat turn's final call leaves room for the answer after thinking: set an explicit output limit (e.g. 16–32k) and/or cap or steer the thinking effort for the chat agent. Check ADK's Anthropic adapter for where max_tokens is set.
- A test pins the limit the Anthropic request carries.
- If a call still ends on max_tokens with no text, the turn retries once without thinking (or with a lower effort) before showing the empty-answer message. Record the retry in turn stats.
- Live: the trace's prompt (a big multi-boss analysis) answers.

## Hazards to design around (PO, read before the first edit)
1. **The system prompt changes every minute.** `build_instruction` (agent.py) ends with `<CURRENT_TIME>` at minute resolution. Anthropic's prefix order is tools → system → messages, so a changed system block invalidates the cached history behind it; a 145 s turn crosses 2–3 minute boundaries. `agent.py` is Nils's file this sprint: solve it inside `model_retry.py` (for example: cache breakpoint before the time block and carry the time block after the cached prefix in the Anthropic request), or post a blocker and I sequence the grant.
2. **Other per-call changes to the prefix:** the round-cap `WRAP_UP_INSTRUCTION` appended to the system instruction, `inject_preamble` on the turn's user message, `trim_old_tool_results`, the thinking-block replay you already rewrite (`drop_block` / thinking binding beta), and the one-time sibling-model switch (021). Know which of them break the cache and say so in the hand-off.
3. **Token accounting:** with caching, Anthropic's `input_tokens` excludes cache reads and writes. Turn stats read `usage_metadata.prompt_token_count` and `cached_content_token_count` in `agent_runner.py` (Edda's file, don't edit): fill those correctly from your side (the `LlmResponse` your `generate_content_async` yields), so `turn stats` shows the full prompt size and `cached_tokens` > 0 without a runner change.
4. **Thinking retry and streaming:** a retry after partial thought parts were already streamed must not duplicate answer text. Record the retry as a `TurnStats` field plus one log line in `model_retry.py`; no new stream event types (the stream protocol is Edda's).
5. **Vertex:** `RetryingClaude` may run on Vertex (provider layer). Breakpoints must work on both, or fall back cleanly.

## Contract you produce: `contract:claude-thinking-summaries` (board, to all)
Edda's status line (080) needs thought text on the Claude path. You own the Anthropic request: make sure the thinking config asks for visible (summarized) thinking text where the API needs it, and that ADK maps it to parts with `thought=True`. Producer test: the request's thinking config. Post "as built" on the key once checked; if the API or adapter can't give text, say so on the key at once so Edda builds the generic fallback.

## File footprint (board `owner:` keys, to vera)
- `wcl_agent/llm/model_retry.py`, `wcl_agent/llm/provider.py`
- `backend/tests/test_model_retry.py`, new `backend/tests/test_079_*.py`
Not yours: `wcl_agent/agent.py` (Nils), `backend/app/agent_runner.py` (Edda). Anything else is a blocker. Prompt budget share: 0 (contract:prompt-budget).

## Live pre-check
Measurement needs the real model: post `live-check:079-pre` early with the exact command (before and after: same prompt, per-call TTFT, `cache_read`/`cache_creation` per call, turn cost; then the big multi-boss prompt from trace 1d8086d1… for sc-567). Team-lead runs it at once. Never call a real model or read `.env` yourself. What only the tip can show goes under `live-check:079`.

## Stories on Shortcut
Move sc-568 and sc-567 to In Progress when you start, Under Review in your hand-off.

## Known facts
- **clock-seam-wall-clock-budgets**: wall-clock budgets read `model_retry._clock`, which tests replace; never patch `time.monotonic` globally.
- **module-state-needs-reset**: `model_retry._limited_until` is process-wide state; a test that trips it needs a reset (autouse fixture in your own module).
- **runner-test-fakes**: the `agent_runner` tests feed `SimpleNamespace` events through fake runners; read event fields with `getattr` and a default.
- **otel-env-strip-in-tests**: `backend/tests/conftest.py` deletes every `OTEL_*` at import; a script starting the backend outside pytest must clear them too.
- **tool-docstring-is-prompt**: test_064 caps instruction plus schemas (12,733 chars/4).
- **wcl-agent-no-backend-imports**: `wcl_agent` never imports `backend`; GenAI spans for wcl_agent live in `generation.py` (OTel API only).
- **pg-tests-shared-db**: Postgres tests share one DB.
