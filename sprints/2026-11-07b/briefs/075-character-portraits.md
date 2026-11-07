# Brief 075-character-portraits

- Feature **075**, branch `075-character-portraits`, tier **M** (one Spec Kit pass, no gates;
  answer clarify yourself as `scope:075:<topic>` decisions). Model opus, effort high.
- Seat **dev-1** (Ansel). Worktree `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at 516aa0d:
  branch from **de66bdd**). Stream type: app full-stack.
- **Security-core: yes** (a client secret, an outbound API, a shared Redis key path, and
  untrusted URLs rendered as images). PO runs one qa-security review at hand-off.
- **No live Blizzard calls by you.** Use fakes. A real API check goes to team-lead as
  `live-check:075-pre` with the exact command (e.g. a one-off script that prints the media
  response shape for one character, never the token).

## Stories (epic 362)
- sc-363 (3) "Fetch and cache character portraits from the Blizzard profile API": "As a player,
  I want the app to look up my characters' portraits (avatar/inset) from Battle.net, so that
  the UI has a real picture to show for each character.
  - Use the Blizzard Profile API character-media endpoint (client-credentials token;
    region/realm/name from the stored character).
  - Cache the image URL per character (Postgres/Redis) with a sensible TTL; don't call Blizzard
    on every page load.
  - Graceful fallback (class icon or initials) when a character is not found, private, or the
    API is down.
  - Serve the URL to the frontend through the existing character/profile responses."
  **Changed AC (PO, on the ticket):** serve them through their own endpoint for the caller's
  profile characters (e.g. `GET /api/profile/portraits` → `{character_id: url | null}` in a new
  router), not inside the profile responses: the profile page must not wait on Blizzard, and
  074 owns the profile responses this sprint. Cache in **Redis only** (no migration).
- sc-364 (3) "Show character portraits wherever a character appears in the UI": "As a player,
  I want my characters' portraits shown next to their names across the app, so that I can
  recognise characters at a glance.
  - One shared avatar component (portrait, with class-icon/initials fallback), used on the
    profile page, sidebar, welcome chat, raids page and chat character mentions where there
    is room.
  - Lazy-load images; no layout shift; works in all themes."
  **Changed AC (PO):** this sprint: profile page (`CharactersTab`), the chat confirmation card
  (`ProposalCard`) and the welcome page's recent raids (`WelcomePanel`). The raids page is being
  rebuilt in parallel (073): its portrait is a follow-up. The sidebar shows no characters.

## Contract you produce (`contract:class-avatar`)
`ClassAvatar({ char: { name, class_name, portrait_url? }, className? })`: existing call sites
(`ProposalCard`, `CharactersTab`, and possibly 073's new raids page) keep working unchanged and
show initials when there is no portrait. Pin it with one test rendering without `portrait_url`.

## File footprint
- Backend: `backend/app/services/portraits.py` (new: Blizzard client + cache),
  `backend/app/api/portraits.py` (new router), `backend/app/main.py` (router registration
  only), `backend/app/config.py` (Blizzard settings; `.env.example` already has
  `BLIZZARD_CLIENT_ID`/`SECRET`), `.env.example` (only if a new setting needs a line),
  `backend/tests/test_075_*.py` (new)
- Frontend: `frontend/src/components/profile/ClassAvatar.tsx`, `CharactersTab.tsx`,
  `frontend/src/components/ProposalCard.tsx`, `ProposalCard.test.tsx`,
  `frontend/src/components/WelcomePanel.tsx`, `frontend/src/api/portraits.ts` (new, on the
  exported `send`; don't edit `restClient.ts`/`types.ts`, they are 074's),
  `frontend/src/hooks/usePortraits.ts` (new), new tests beside them
- `specs/075-character-portraits/**`

## Hostile inputs (rule 10: one test each, asserted where the guard takes effect)
- Realm or name with `/`, `\`, `..`, `?`, `#`, `%2F`, a newline, unicode → the outbound URL is
  built with proper path encoding and its host and path prefix are fixed (assert on the URL the
  fake HTTP client actually received).
- Region from stored data outside the known set (`eu`, `us`, `kr`, `tw`) or with a host-ish
  value (`eu.evil.example`) → no request.
- The media response's image URL: only `https` on Blizzard's render host(s) is stored or served;
  `javascript:`, `data:`, `http:`, another host, a `\`-host trick (`https://render.worldofwarcraft.com\@evil.example`)
  → null (assert on what the endpoint returns, which is what `<img src>` gets).
- Redirects from Blizzard → not followed to another host; a huge body → bounded read; timeout
  → fallback, the page still loads.
- The token and client secret never appear in logs, errors, cache values or responses.
- Redis key from a character's realm/name: normalised, length-capped, no key injection
  (`:` or `*` in a name), and the cache never lets workspace A's request decide which
  character workspace B's endpoint returns. The endpoint only covers characters in the
  caller's own profile, read on the server, never names from the query.
- Blizzard down or rate-limiting → bounded: no call per page load, a negative-cache entry
  with a shorter TTL.
- One mutate.py bite per guard (URL host check, region allow-list, scope to own profile).

## Live pre-check
Post `live-check:075-pre` with the exact command for the one real response shape you need.

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

Team facts for `backend/app/config.py`, `backend/app/main.py`, `frontend/src/components/profile/ClassAvatar.tsx`, `frontend/src/components/profile/CharactersTab.tsx`, `frontend/src/components/ProposalCard.tsx`, `frontend/src/components/WelcomePanel.tsx`, and the paths you run: `.claude/team/check.py`, `.claude/team/browse.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **telemetry-config-no-app-config** (direct: file:backend/app/config.py; verified 32010a6 2026-11-05): Importing `backend.app.config` loads ADK and FastAPI, and telemetry has to start before both. So `backend/app/telemetry/config.py` reads `os.environ` itself (it loads `.env` the way config.py does and honours `WCL_LOAD_DOTENV`) and must never import `backend.app.config`. A setting the telemetry bootstrap needs goes into its own env read, not into `Settings`.
- **vitest-no-jest-dom** **STALE** (file: file:frontend/src/ contains frontend/src/components/profile/ClassAvatar.tsx; verified 1ee750a 2026-11-05): The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like `toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
- **chat-drop-ends-turn-locally** (neighbour: file:frontend/src/App.tsx called by frontend/src/components/WelcomePanel.tsx::errorText; verified 32010a6 2026-11-05): App.handleStatus ends a streaming turn when the socket drops (partial text kept, note in the error line, composer free); the next open reloads that chat (reloadAfterDrop). The backend saves a status=partial message only when the process survives (_persist_partial); after a restart the reload re-appends the local partial. The Composer is disabled while disconnected, so tests cannot click send mid-drop. Partial and `done` answers go only into the open chat; dropRef is cleared by sendText and selectConversation.
- **faro-lazy-context** (neighbour: file:frontend/src/telemetry/faro.ts called by frontend/src/components/WelcomePanel.tsx::load; verified b9cf9a3 2026-11-05): The Faro packages load only through the dynamic `import()` in `telemetry/faro.ts`, and `context.ts` imports types only. New Faro-facing code (the socket, the REST client, error boundaries) calls `context.ts` functions, which are no-ops until `registerFaro`. Never add a static `@grafana/faro-react` import: it pulls Faro into the main bundle. That is why 060 wrote its own error boundary instead of `FaroErrorBoundary`.
