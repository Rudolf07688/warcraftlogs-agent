# Brief 063-chat-reconnect (tier S)

- Feature 063, branch `063-chat-reconnect`. Seat dev-2 (Tomas). Model sonnet, effort high.
- Worktree `/home/rudolf/dev/wcl-worktrees/dev-c`, base ref `sprint-2026-11-05b` (0678ea7).
- Parallel developers: Nils (061, KB), Ansel (062, observability), the dev-4 holder (064, agent instruction). Disjoint footprints.
- Not security-core (the note is static text; the partial answer keeps its existing renderer). No migration.

## Footprint
`frontend/**` only. The backend is read-only for you: if the saved partial answer does not exist on the backend after a drop, say so in the hand-off (and on the board) rather than changing backend code; the reload then shows whatever the backend saved.

## Story (acceptance criteria verbatim)

### Arch review: chat input stays locked after the connection drops mid-answer (sc-376, 2 pts)
If the WebSocket drops while Barnaby is answering (backend restart, network blip, proxy timeout), the chat input stays disabled until the user reloads the page.
Why (read from the code, not yet reproduced live): `frontend/src/App.tsx` sets `streaming = true` when a question is sent; only a `done` or `error` frame sets it back to false. `frontend/src/api/wsClient.ts` `onclose` only reports `connected = false` and reconnects after 1.5 s. The new socket has no turn running, so no `done`/`error` frame ever arrives. The composer is `disabled={streaming || !connected}`, so after the reconnect it stays locked; the partial answer is left half-rendered.

Acceptance:
- When the socket closes while a turn is streaming, the frontend ends the turn locally: unlock the composer, keep the partial text, and show a short "connection lost, the answer may be incomplete" note.
- After the reconnect, reload the active conversation so the saved (partial) answer from the backend replaces the local copy.
- A vitest covers: send -> socket close -> composer enabled again.

## Edge cases first (test these)
1. Close while **not** streaming: no note, no reload, nothing changes except `connected`.
2. Close during streaming, then the user switches conversation before the reconnect: reload only the conversation that was active at the drop, and only if it is still active; never overwrite another conversation's messages.
3. Several closes in a row (flapping): one note, one reload after the socket that finally opens.
4. A late `done`/`error` frame for the dropped turn must not be possible on the new socket, but if any stray frame arrives after the local end, it must not re-lock the composer or duplicate the message.
5. A pending confirmation card or a tool-in-progress indicator at the drop: it must stop spinning (end of turn), not stay "in progress".
6. The partial text is kept until the reload replaces it; if the reload fails (backend still down), the partial text and the note stay.
7. `streamStore` (PERF-010) holds the streaming text: make sure ending the turn flushes it into the message list exactly once.
Stay minimal: the note is one line of copy in the existing message style, no new component library.

## Process (all streams)
- Tier S: post a short plan on the board (`decision`, key `plan:<NNN>`), then implement. No Spec Kit.
- Branch `<NNN>-<short-name>` from the base ref, in your worktree. Stay inside the footprint; if a root cause sits outside it, post a `question` on the board naming the file and hunk, and keep going on the rest.
- Move your stories to In Progress when you start and to Under Review in your hand-off (Team 1, Standard workflow: In Progress 500000008, Under Review 500000023). Never Done.
- **Team facts (P13 trial, first sprint):** run `python3 .claude/team/facts.py for <path>` before you change a file you haven't read yet; trust what it says, re-check anything marked STALE. When you learn something about this code that the next developer would otherwise rediscover (a trap, a contract, a non-obvious cause), add it with `facts.py add` and commit the fact file on your branch. Name the facts you used and the ones you added in the hand-off.
- Checks: `python3 .claude/team/check.py run --as <your-name>` on your final committed clean tree (the RECEIPT is what lets me merge without re-running). GitNexus `detect-changes --scope all` before each commit.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never push. Never commit CLAUDE.md, AGENTS.md, todo.md, the constitution or .specify/feature.json.
- **Hand-off:** post a board `handoff` (key `status:<NNN>`) and return the same as your result: branch, commits, files, the check.py RESULT and RECEIPT lines, the AC-to-test mapping, risks, a **live-check** suggestion (prompt or action plus the expected facts), facts used/added, and one line starting `Retro:` (what helped or slowed you this run, for the team retro).

## Known facts for this footprint

Team facts for `frontend/src/App.tsx`, `frontend/src/api/wsClient.ts`, `frontend/src/` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **faro-lazy-context** (direct: file:frontend/src/telemetry/context.ts is inside frontend/src/; verified b9cf9a3 2026-11-05): The Faro packages load only through the dynamic `import()` in `telemetry/faro.ts`, and `context.ts` imports types only. New Faro-facing code (the socket, the REST client, error boundaries) calls `context.ts` functions, which are no-ops until `registerFaro`. Never add a static `@grafana/faro-react` import: it pulls Faro into the main bundle. That is why 060 wrote its own error boundary instead of `FaroErrorBoundary`.
- **vitest-no-jest-dom** (direct: file:frontend/src/; verified b9cf9a3 2026-11-05): The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like `toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
