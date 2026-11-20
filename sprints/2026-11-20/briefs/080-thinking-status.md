# Brief 080-thinking-status (dev-5 Edda)

- **Feature / branch:** 080 / `080-thinking-status`
- **Tier:** M: one Spec Kit pass, no gates; answer your own clarify questions on the board (`scope:080:<topic>`).
- **Model / effort:** opus, high
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-c` (detached at the base). **Base ref:** `d7dab27`.
- **Seat:** dev-5 (Edda). In parallel: Tomas (078, WCL tools), Vera (079, Anthropic request in `model_retry.py`), Ansel (081, boss mechanics), Nils (082, owns `wcl_agent/agent.py` and the prompt).
- **Security-core: yes** (D18): you render model output in the chat and change what `ws.py` saves. I run a `qa-security` review on your branch at hand-off; its Highs and Mediums are your one rework round.
- **Migration:** none.

## Stories (acceptance criteria verbatim)

### sc-569 (3 pts, feature): Show what the agent is thinking between tool rounds (live status line from thinking summaries)
Owner, 2026-11-07: "it would like use 3 tools and then there is this gap where it looks like nothing is happening. If that's the agent thinking / reasoning then maybe there should be some UI feedback indicating that." The agent runs with `include_thoughts=True`; the model streams short thinking summaries; `agent_runner.py` drops these `thought` parts. In the owner's trace the gaps were 17–68 s per model call.
AC:
- While the model thinks, the chat shows a one-line status under the spell card, updated from the latest thought summary (first sentence, trimmed to about 80 chars), styled as transient. It's never saved as part of the answer and never shown after the answer starts.
- A new stream event type (e.g. `{"type":"thinking","text"}`), throttled (no more than about 1 update/s), added to the stream protocol docs and the frontend types.
- Without summaries (thinking off, or a model that sends none), a generic "Thinking…" with elapsed seconds after about 3 s of silence.
- Thought text is model output: render as plain text, length-capped, never markdown or HTML.
- Works for Gemini and Claude.

### sc-572 (2 pts, bug), structural part: Tool troubleshooting leaks into the coach's answers
Text the model writes between tool rounds streams to the user and stays in the answer (e.g. "Warcraft Logs is throwing server errors on the raid reports' player lists. I'll go through her own boss history … I'll retry with it and pull her casts and buffs."). Goal: the answer the user keeps starts at the verdict; progress between tool rounds is still visible while the turn runs, but as transient status (pairs with sc-569), not as part of the stored answer.
Your ACs (decision:572-split):
- A turn with tool rounds stores and shows only the final answer text; interim text appears only as status while running.
- Reload shows the same answer as the live stream.
Not yours: "a turn whose tools fail says so once, plainly" is a prompt line Nils writes in `<TOOL_FAILURES>`.

## Design notes and hazards (PO)
- **Where the protocol lives:** the `_run_turn` docstring in `backend/app/agent_runner.py` is the stream protocol doc in code; add the new event(s) there and in `frontend/src/types.ts`. The architecture page `documentation/architecture/pages/streaming.html` is updated in the close-out docs pass, not by you.
- **Interim text is only known as interim after the fact:** text streams as `token` before the model decides to call a tool. Whatever you choose (retract the segment on the next `tool_start`, or a segment marker), the browser and `ws.py`'s accumulated `tokens` must agree, so the live view equals the reload. Fact `runner-outcome-flag-on-record`: tell `ws.py` with a flag on the record, never by matching text.
- **Every save path:** the final save, `_persist_partial` on a superseded turn (076, sc-511), a dropped socket (fact `chat-drop-ends-turn-locally`), and the no-answer closing token. Decide what a turn interrupted during an interim segment saves, record it as `scope:080:partial-save`, and test it.
- **Shared runner:** `stream_response`/`_run_turn` also serve the greeting, guide jobs and evals (`USER_ID`); keep their output unchanged (fact `stream-response-shared-by-jobs`, GitNexus CRITICAL).
- **Throttle and order:** at most ~1 thinking event per second per turn; no thinking event after the first answer token of the final segment; nothing from a superseded turn may reach the new turn's view.
- **Claude thought text:** Vera (079) owns the Anthropic request and the `contract:claude-thinking-summaries` key; consume it with one test from your side (a fake part `thought=True` with text yields a thinking event). If Vera's "as built" says Claude sends no text, the generic "Thinking…" path covers it.
- **Turn stats log line** in `stream_response` stays as it is (Vera records her retry on `TurnStats` herself).

## Hostile inputs (test each where the guard takes effect: the DOM, the stored message, the frame sent)
- thought text with HTML or markdown: `<img src=x onerror=alert(1)>`, `[x](javascript:alert(1))`, `**bold**`, a code fence
- a 10,000-char thought with no sentence end; newlines, control characters, ANSI escapes and bidi overrides in a thought
- a thought arriving after the final answer started (must not show), and thought parts from the web-search sub-agent
- interim text containing report codes, source ids and "retry" lines: never in the stored message, never in the KB chat index
- a turn superseded or dropped during an interim segment (what is saved, what the new turn shows)
- a client frame of the new type sent to the server (the server must ignore it)

## File footprint (board `owner:` keys, to edda)
- `backend/app/agent_runner.py`, `backend/app/api/ws.py`
- `frontend/src/**` (only you touch the frontend this sprint)
- new `backend/tests/test_080_*.py`, `specs/080-thinking-status/**`
- An existing runner or ws test you must change (`test_046_empty_turn`, `test_tool_start_once`, `test_turn_path`, `test_048_empty_outcome`, `test_proposal_ws`, …): post a blocker naming it and I grant it at once.
Prompt budget share: +50 tokens (contract:prompt-budget).

## Live pre-check
Whether Claude and Gemini actually stream thought text through ADK needs the real model: post `live-check:080-pre` early with the exact command (a chat turn on each provider, log the thought parts' lengths, never their content into the board). Team-lead runs it at once. End-of-sprint steps (status line visible during a long turn; reload equals live; no troubleshooting paragraph in the stored answer) go under `live-check:080`.

## Stories on Shortcut
Move sc-569 and sc-572 to In Progress when you start. In the hand-off move sc-569 to Under Review; leave sc-572 In Progress (I move it once Nils's half is merged too).

## Known facts
- **runner-outcome-flag-on-record**: tell `ws.py` about a turn's outcome with a flag on the yielded record; the closing no-answer token carries `"empty": True`, which `ws.py` pops before sending.
- **runner-test-fakes**: runner tests feed `SimpleNamespace` events through fake runners (`test_046_empty_turn`, `test_tool_start_once`, `test_context_injection`, strict `run_async` kwargs); read fields with `getattr` and a default.
- **stream-response-shared-by-jobs**: `stream_response`/`_run_turn` serve chat turns and greeting, guide jobs and evals (`USER_ID`); chat-only behaviour keys on `user_id != USER_ID`. GitNexus rates both CRITICAL.
- **ws-turn-single-flight-per-chat**: one turn at a time per chat (sc-511); a newer turn cancels the old one only in setup or streaming, waits `SUPERSEDE_WAIT_S`, then writes. Two turns on one chat in a test supersede each other.
- **ws-refresh-actor-patch-signature**: ws tests patch `ws_mod.set_refresh_actor` with `lambda *_: None`; adding a keyword argument at its call site breaks them all.
- **ws-test-helpers**: reuse `_identity`, `_quiet`, `_ctx_stream`, `_tool_end`, `_run` from `backend/tests/test_proposal_ws.py`.
- **chat-drop-ends-turn-locally**: `App.handleStatus` ends a streaming turn when the socket drops (partial kept); the next open reloads the chat; the backend saves a `status=partial` message only when the process survives.
- **app-tests-mock-router-usematch**: App.test.tsx and App.reconnect.test.tsx mock react-router-dom as `{ useNavigate, useMatch: () => null }`; a new router hook in App.tsx must be added to both mocks.
- **vitest-no-jest-dom**: no jest-dom matchers; assert on `textContent`, `toBeTruthy()` and plain values.
- **faro-lazy-context**: never a static `@grafana/faro-react` import; call `telemetry/context.ts` functions.
- **metric-attributes-allowlist**: a new metric label survives only if in `setup.METRIC_ATTRIBUTES` (namespaced `app.*`).
