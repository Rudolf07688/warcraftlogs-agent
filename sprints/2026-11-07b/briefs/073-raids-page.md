# Brief 073-raids-page

- Feature **073**, branch `073-raids-page`, tier **M** (one Spec Kit pass, no gates; answer
  clarify yourself as `scope:073:<topic>` decisions). Model sonnet, effort high.
- Seat **dev-2** (Tomas). Worktree `/home/rudolf/dev/wcl-worktrees/dev-b`. Stream type: app frontend.
- Security-core: no (it renders stored WCL text: render as text, never as HTML).

## Stories (epic "Rework Raids page", 106)
- sc-141 (2) "Raids page: tabs instead of dropdown": "As a user, I want to switch raids with
  tabs instead of a dropdown, so it's quicker."
- sc-143 (1) "Raids page: \"Analyze this raid\" new-chat button": "As a user, I want a button
  that starts a new chat with the analyze prompt."
- sc-142, UI half (2 of 5) "Raids page: show previously pulled raid data": "As a user, I want
  each raid to show stored data (participants, duration, my character's parse), so I can
  review it without a chat." Nils builds the endpoint in 072.
- Epic text (owner's todo): "Rework Raids page — make tabs instead of dropdown; show previously
  pulled data from that raid (participants, duration, my character's parse etc); add button to
  start a new chat with the current 'analyze this raid' message."

## Design decision (PO, `decision:raids-page-design`)
Today the raids are a collapsible list in the sidebar ("the dropdown"); clicking one starts
an investigation chat at once (`handleInvestigateRaid` in App.tsx). The rework:
- A Raids page (inside the app shell, e.g. `/app/raids/:reportCode?`, so the chat socket and
  `handleInvestigateRaid` stay where they are) with **one tab per tracked raid**, most recent
  first, using the existing shadcn `components/ui/tabs.tsx`. The tab list scrolls
  horizontally at 390px; the URL selects the tab (deep link, back button works).
- The sidebar's collapsible raid list becomes one "Raids" entry (with the count) that opens
  the page; clicking it no longer starts a chat.
- Each tab shows the raid's label, date, boss summary (already in `Raid`) and the stored data
  from `contract:raid-summary`: duration, participants (grouped by role is fine), and my
  characters' parses. Loading, `has_data: false` ("Nothing stored for this raid yet: analyze
  it to pull its data") and error states.
- The **"Analyze this raid"** button starts a new chat with the current analyze message, by
  reusing the existing `investigateRaid` + `sendText` flow (DRY: no second implementation).
- Keep it lightweight; no portraits this sprint (075 builds them in parallel; follow-up).

## Contract you consume (`contract:raid-summary`; producer Nils, 072)
`GET /api/raids/{report_code}/summary` → 200
```json
{
  "report_code": "a1B2c3D4e5F6g7H8",
  "has_data": true,
  "duration_ms": 9876000,
  "participants": [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement", "role": "dps"}],
  "my_characters": [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement",
                     "parses": [{"encounter": "Ulgrax the Devourer", "difficulty": "Heroic", "percentile": 87.4}]}],
  "fetched_at": "2026-11-07T19:00:00Z"
}
```
404 when the raid isn't tracked by the caller; `has_data: false` with nulls/empty lists when
nothing is stored; each part may be missing on its own. Write one test against this example
from your side (mocked fetch). An "as built" update on the key replaces the example.
`contract:class-avatar`: you may render `ClassAvatar` from `components/profile/ClassAvatar.tsx`
with `char={{name, class_name}}`; Ansel keeps that call working.

## File footprint
- `frontend/src/pages/RaidsPage.tsx` (new) and `frontend/src/components/raids/**` (new)
- `frontend/src/api/raidSummary.ts` (new: the summary type and the call, built on the exported
  `send` from `api/restClient.ts`; do **not** edit `restClient.ts` or `types.ts`, they are 074's)
- `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/routes.tsx`
- Tests: `frontend/src/App.test.tsx`, `App.reconnect.test.tsx`, `App.modelFallback.test.tsx`,
  `routes.test.tsx`, new `*.test.tsx` beside your new files (tests that `vi.mock` restClient
  must also mock `send` if your module is reached)
- `frontend/src/styles.css`, `frontend/src/index.css` (only if Tailwind classes can't do it)
- `specs/073-raids-page/**`

## Hostile inputs
- A raid label, guild, zone or player name containing `<img src=x onerror=…>` or markdown →
  shown as text. A 300-char name → truncated with CSS, no layout break at 390px.
- A `reportCode` in the URL that isn't in the raid list (or `..%2F`, encoded slashes) →
  a "raid not found" state, no request built from an unencoded path segment
  (`encodeURIComponent`, as `investigateRaid` does).

## Live pre-check
If a question needs the real stack, post `live-check:073-pre` with the exact command; team-lead
runs it at once. Use `browse.py` with mocked API responses for your own UI checks.

## Common rules for this sprint
- Base ref **de66bdd** (sprint branch tip; restClient `send` is exported there). Create your
  branch from it in your worktree. Never push, never merge, never move a ticket to Done.
- Parallel streams: 072 Nils (dev-3), 073 Tomas (dev-2), 074 dev-5 (new seat), 075 Ansel
  (dev-1), 076 Vera (dev-4). PO is Maren (`--to maren` not needed for questions).
- Footprint: only the files below (board `owner:` keys). Shared files (`backend/app/schemas.py`,
  `backend/app/db/repository.py`, `backend/app/db/models.py`, `backend/app/api/profile.py`,
  `frontend/src/types.ts`, `frontend/src/api/restClient.ts`) belong to 074 alone; everyone
  else keeps new types and calls in their own new modules. Need anything outside: `blocker`.
- **Live pre-check:** if a question needs the real stack (real LLM, WCL, Blizzard, `.env`),
  post a `question` keyed `live-check:<NNN>-pre` with the exact command while building;
  team-lead runs it at once. End-of-sprint live steps go under `live-check:<NNN>`.
- Testing (D21): targeted tests while building; one honest contract test per promise; hand-off
  receipt `python3 .claude/team/check.py run --as <you> --base de66bdd` on your committed head.
- Hand-off as in `developer.md` (about 20 lines, AC mapping, RESULT line, `Retro:` line).
## Known facts for this footprint

Team facts for `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/routes.tsx`, `frontend/src/api/restClient.ts`, `frontend/src/App.test.tsx`, and the paths you run: `.claude/team/browse.py`, `.claude/team/check.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **chat-drop-ends-turn-locally** (direct: file:frontend/src/App.tsx; verified 32010a6 2026-11-05): App.handleStatus ends a streaming turn when the socket drops (partial text kept, note in the error line, composer free); the next open reloads that chat (reloadAfterDrop). The backend saves a status=partial message only when the process survives (_persist_partial); after a restart the reload re-appends the local partial. The Composer is disabled while disconnected, so tests cannot click send mid-drop. Partial and `done` answers go only into the open chat; dropRef is cleared by sendText and selectConversation.
- **vitest-no-jest-dom** **STALE** (file: file:frontend/src/ contains frontend/src/App.tsx; verified 1ee750a 2026-11-05): The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like `toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
- **cache-get-or-load-critical** (neighbour: sym:wcl_agent/cache/cache.py::_shared calls frontend/src/App.test.tsx::MessageList; verified b9cf9a3 2026-11-05): GitNexus rates `get_or_load` and `_shared` CRITICAL (63 upstream at b9cf9a3): every cached WCL read goes through them. Keep changes additive: don't change values, TTLs, locks or the unshareable handling. Run the full suite and the cache tests (`test_wcl_cache`, the 047 local-rate tests) before hand-off.
- **cache-single-flight-starter-context** (neighbour: sym:wcl_agent/cache/cache.py::_shared calls frontend/src/App.test.tsx::MessageList; verified b9cf9a3 2026-11-05): Both single-flights, the cache's `_shared` and `AsyncWCLClient.query`, run the shared task in the STARTER's copied context: every ContextVar read inside the load (`_Load`, tenant, turn) is the first caller's. If the answer depends on the caller, key the flight by that scope (the client appends `source.scope()`, the tenant) or let joiners reload: in the cache, a joined unshareable load runs its own `_lookup`.
- **faro-lazy-context** (neighbour: file:frontend/src/telemetry/context.ts called by frontend/src/api/restClient.ts::send; verified b9cf9a3 2026-11-05): The Faro packages load only through the dynamic `import()` in `telemetry/faro.ts`, and `context.ts` imports types only. New Faro-facing code (the socket, the REST client, error boundaries) calls `context.ts` functions, which are no-ops until `registerFaro`. Never add a static `@grafana/faro-react` import: it pulls Faro into the main bundle. That is why 060 wrote its own error boundary instead of `FaroErrorBoundary`.
- **redis-cache-tenantless** (neighbour: file:wcl_agent/cache/cache.py calls frontend/src/App.test.tsx::MessageList; verified b9cf9a3 2026-11-05): The shared Redis cache is tenant-less: keys never hold a user, tenant or conversation id, every workspace reads the same entry, and loaders back-fill it on a miss. A load that served data only one tenant may see (a grant-only raw-store hit) must call `mark_unshareable()`, so the result skips Redis and the memo. Any new read layer under `get_or_load` that serves tenant-private data without that mark leaks it to every workspace.
