# Brief 085: status frames and turn costs (socket and UI)

- **Feature / branch:** 085, `085-status-frames`. **Tier M** (one Spec Kit pass, no gates; answer your own clarify questions as `scope:085:<topic>`).
- **Seat:** dev-5 (Edda). **Model/effort:** opus high (cancel races, stored partials, rendering model text).
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached). **Base ref:** `sprint-2026-11-22` at 4fc12a3.
- **In parallel:** Vera (dev-4, 084: model re-runs and `backend/app/agent_runner.py`), Ansel (dev-1, 086 mechanics notes and rankings).
- **Security-core: yes** (D18: renders model text, stores partial answers). The PO runs a qa-security review at hand-off. No migration.

## Stories and acceptance criteria (verbatim from the tickets)

**Thinking status edge cases (sc-582), your part: socket and UI.** (The runner items BUG-005, BUG-006, SPEC L1 and the short-answer residual are Vera's in agent_runner.py.)
- BUG-004: a cancel from a second tab landing exactly during the interim send keeps the retracted progress text in that turn's saved partial; reload then differs from the old tab.
- D18 SEC-002 residual: an interim frame lost in transit leaves the retracted text local-only (not stored, not in the PDF, gone on reopen).
- Edda's backlog:status-under-cards-retry: model_retry/model_fallback labels never show once spell cards exist; show them in the 080 status line.

**Small chat-turn costs (sc-583), your part.**
- 082b: `ws.py::_build_turn_preamble` reads the whole profile-settings row plus an onboarding query whose result is dropped: select only main_class/main_spec (1 line).
- 080: the thinking status line lives in App state (`frontend/src/App.tsx`), so every thinking frame (≤1/s) and every non-token frame re-renders App and the message list; use a small store like the streamed answer text (`frontend/src/lib/streamStore.ts`).
(The damage_fields note and mechanics schema items are Ansel's.)

## Contract
`contract:chat-status-records` (posted by the PO): the `thinking`, `interim`, `model_retry` and `model_fallback` record shapes are those on base 4fc12a3; 084 changes when they are sent, not their shape. Write one test from your side against that example.

## File footprint (board `owner:` keys)
- `backend/app/api/ws.py`
- `backend/app/db/repository.py`: one narrow read for main_class/main_spec (no other change)
- `frontend/src/**`
- tests: new `backend/tests/test_085_*.py`; existing `backend/tests/test_080_thinking_ws.py`, `backend/tests/test_082b_preamble_main.py`
- `specs/085-status-frames/**`, `.claude/team/facts/`
Not yours: `backend/app/agent_runner.py` (Vera). If a fix needs it, post `ask:backend/app/agent_runner.py`; the PO sequences it after 084 merges.

## Hostile inputs (one test each, before the code; assert where the guard acts: what is stored, sent or rendered)
- a status/interim text with HTML, markdown links/images, a `<script>` tag, zero-width and RTL-override characters: rendered as plain text, clamped as today
- a `model_retry`/`model_fallback` frame whose model id or numbers are odd (very long id, markup in the id, negative/NaN wait): the label renders plain and bounded
- a cancel from a second tab arriving during the interim send, and during the save: the stored partial equals what a reload shows (no retracted text)
- an interim frame dropped in transit (client never sees it): stored, PDF and reopened text agree
- a forged client frame claiming `interim`/`thinking` (client-to-server): ignored, never stored
- the preamble read for another tenant's settings row: only the caller's tenant (RLS), and nothing but main_class/main_spec selected

## Bounds
- rate: thinking frames stay ≤ 1/s into the store; the store update must not re-render App or the message list (test: a burst of 50 thinking frames renders the list once / App render count stays constant)
- size: status/label text clamped (existing `STATUS_MAX` style constant); a stored partial never larger than the answer tokens it keeps
- held resources: no DB session or lock held across the frame send or the cancel wait (`SUPERSEDE_WAIT_S`); test the cancel path
- growth: no per-frame DB write (at most the existing saves per turn)

## Live pre-check
If a question needs the real stack, post `live-check:085-pre` (kind `question`) with the exact steps while you build; team-lead runs it at once. Browser checks: `browse.py` on your own `stack.py` stack.

## Known facts

Team facts for `backend/app/api/ws.py`, `frontend/src/App.tsx`, `frontend/src/components/MessageList.tsx`, `frontend/src/api/wsClient.ts`, and the paths you run: `backend/tests/test_080_thinking_ws.py`, `frontend/src/App.thinking.test.tsx` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **app-tests-mock-router-usematch** (direct: file:frontend/src/App.tsx; verified 8986855 2026-11-20): App.test.tsx and App.reconnect.test.tsx mock react-router-dom as { useNavigate, useMatch: () => null }: any new react-router hook App.tsx calls must be added to both mocks, or every App test throws. App.modelFallback.test and App.raids.test use a real MemoryRouter instead (App has no Routes of its own, so initialEntries picks /app or /app/raids/:code).
- **app-tests-real-messagelist-scrollto** (direct: file:frontend/src/components/MessageList.tsx; verified 3dcf75c 2026-11-20): App tests that render the real MessageList must stub HTMLElement.prototype.scrollTo (jsdom lacks it): on 'done' ScrollToQuestion scrolls the question into view, the throw is caught by the telemetry error boundary and the page silently renders no messages, so assertions fail with an empty list rather than an error. Also stub ResizeObserver for use-stick-to-bottom. See App.thinking.test.tsx.
- **chat-drop-ends-turn-locally** (direct: file:frontend/src/App.tsx; verified 8986855 2026-11-20): App.handleStatus ends a streaming turn when the socket drops (partial text kept, note in the error line, composer free); the next open reloads that chat (reloadAfterDrop). The backend saves a status=partial message only when the process survives (_persist_partial; none if a newer turn took the chat); after a restart the reload re-appends the local partial. The Composer is disabled while disconnected: no send mid-drop in tests. Partial and `done` go only into the open chat; sendText and selectConversation clear dropRef.
- **runner-interim-retraction** (direct: sym:backend/app/api/ws.py::_run_chat_turn is in backend/app/api/ws.py; verified 8986855 2026-11-20): On chat turns an 'interim' record means: all answer text streamed so far was progress; ws.py clears its tokens (after sending the frame), App clears streamRef. Only text <= INTERIM_MAX_CHARS, not next to a PRESENTING_TOOLS call, is retracted, never after text was kept; a turn ending without an answer re-emits the retracted text as a token. Answer = tokens after the last interim. Jobs (USER_ID) get none of this. 'thinking' needs event.author == runner.agent.name in fakes.
- **runner-outcome-flag-on-record** (direct: file:backend/app/api/ws.py; verified 8986855 2026-11-20): To tell `ws.py` about a turn's outcome, put a flag on the yielded record, never match on its text. The closing no-answer token carries `"empty": True`; `ws.py` pops it before sending (the wire frame is unchanged) and then skips the KB offer, the title and follow-up suggestions.
- **ws-refresh-actor-patch-signature** (direct: file:backend/app/api/ws.py; verified 8986855 2026-11-20): The ws tests (`test_turn_path`, `test_048_empty_outcome`, `test_model_fallback_ws`, `test_conversation_titles` and others) patch `ws_mod.set_refresh_actor` with `lambda *_: None`. Adding a keyword argument where `ws.py` calls it breaks all of them. Add a new function instead, as `abandon_turn` did.
- **ws-test-helpers** (direct: file:backend/app/api/ws.py; verified 8986855 2026-11-20): For backend WebSocket tests, reuse the helpers in `backend/tests/test_proposal_ws.py` (`_identity`, `_quiet`, `_ctx_stream`, `_tool_end`, `_run`) rather than building a new chat harness.
- **ws-turn-single-flight-per-chat** (direct: sym:backend/app/api/ws.py::_ChatTurn is in backend/app/api/ws.py; verified 20d4197 2026-11-07): One turn at a time per chat, across sockets (sc-511): _ChatTurn.turns is keyed (tenant, conversation), claimed after the ownership check, released in _handle_turn's finally. A newer turn cancels the old one only in setup or streaming (not while it saves), waits SUPERSEDE_WAIT_S, then writes. Each turn is its own task under _start_turn, so a cancel never closes the socket. Tests running two turns on one chat at once will supersede each other.
- **pg-tests-shared-db** (file: file:backend/tests/ contains backend/tests/test_080_thinking_ws.py (you run it); verified 8986855 2026-11-20): The Postgres tests (`*_pg.py`, `test_rls.py`, via `TEST_DATABASE_URL`) share one long-lived database with no reset between tests. Use unique test data (fresh UUIDs and report codes), and never assert exact result lists over global tables (`raw_fetches`, `kb_chunks`, `spec_guides`): other tests' rows are there too.
- **vitest-no-jest-dom** (file: file:frontend/src/ contains frontend/src/App.tsx; verified 8986855 2026-11-20): The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like `toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
- **faro-lazy-context** (neighbour: file:frontend/src/telemetry/context.ts called by frontend/src/api/wsClient.ts::endChatSend; verified b9cf9a3 2026-11-05): The Faro packages load only through the dynamic `import()` in `telemetry/faro.ts`, and `context.ts` imports types only. New Faro-facing code (the socket, the REST client, error boundaries) calls `context.ts` functions, which are no-ops until `registerFaro`. Never add a static `@grafana/faro-react` import: it pulls Faro into the main bundle. That is why 060 wrote its own error boundary instead of `FaroErrorBoundary`.
- **profile-context-class-from-known-player** (neighbour: sym:backend/app/services/profile_context.py::build_preamble called by backend/app/api/ws.py::_build_turn_preamble; verified 9cbc701 2026-11-20): A profile character can have active_spec but class_name None (class resolved later); the KNOWN PLAYER CONTEXT line then read only 'Frost' and the agent asked Frost Mage or DK. build_preamble fills a missing class from the known_players entry with the same name+server+region (never name alone) and lists the workspace's main_class/main_spec (ProfileSettings) when passed. ws._build_turn_preamble passes the main (082b).

(4 more: `facts.py brief --all ...`)
