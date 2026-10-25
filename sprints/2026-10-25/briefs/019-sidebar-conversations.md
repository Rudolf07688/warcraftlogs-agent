# Brief 019 — Sidebar & conversations: order, pinning, generated names (plan F2 / 019)

| Field | Value |
|---|---|
| Feature number | 019 |
| Branch | `019-sidebar-conversations` (set `GIT_BRANCH_NAME=019-sidebar-conversations` for `/speckit-specify`) |
| Spec dir | `specs/019-sidebar-conversations/` |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-b` (track B) |
| Base ref | `sprint-2026-10-25` tip (see `git -C /home/rudolf/dev/wcl-worktrees/sprint rev-parse sprint-2026-10-25`; the worktree is detached there) |
| Model / effort | opus / medium |
| Shortcut stories, in order | sc-154 (1), sc-165 (3), sc-155 (3) |
| Peer developer | `dev-a-018` (track A, `wcl_agent` restructure; it merges first, and you rebase on it) |
| Scrum master | `scrum-master` (your only channel upward) |
| Plan | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/plan.md` (section F2 / 019, plus the "Same-file overlaps" table) |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |
| Decisions | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/decisions.md` |

Note: an earlier brief 019 (security hardening) was withdrawn when the product owner
moved those QA stories out of the sprint. This brief replaces it. Ignore any
`specs/019-security-hardening/` leftovers.

## Plan section (verbatim)

## F2 / 019 — Sidebar & conversations: order, pinning, generated names (Track B, first)

- **Stories, in order:** sc-154 (1) Sidebar: previous conversations above Raids; sc-165
  (3) Pinnable chats in chat window and sidebar; sc-155 (3) Auto-generate conversation
  names.
- **Why bundled:** all three change `Sidebar.tsx` and the conversations API and model.
- **Complexity:** medium.
- **Footprint:** `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx` (chat
  header), `frontend/src/types.ts`, `frontend/src/api/restClient.ts`,
  `backend/app/api/conversations.py`, `backend/app/db/models.py` (`Conversation`),
  `backend/app/db/repository.py` (the title logic around line 130), migration `0012_*`,
  a small title service under `backend/app/services/`, and (sc-155 only) a
  turn-completion hook in `backend/app/api/ws.py` or `agent_runner.py`.
- **Depends on:** sc-155 waits until F1 is merged.
- **Acceptance criteria:**
  1. *(sc-154)* The Conversations section is above the Raids section in the sidebar.
     Both keep their collapse toggles and counts.
  2. *(sc-165)* The user can pin and unpin a chat from its sidebar entry and from the
     open chat's header. Pinned chats appear in a "Pinned" group at the top of the
     conversation list, and the state survives a reload and a re-login.
  3. *(sc-165)* Pinning is stored server side (`pinned_at` nullable column, migration
     `0012`, upgrade and downgrade both work). It goes through a tenant-scoped API
     (for example `PATCH /api/conversations/{id}`) that respects tenancy/RLS: pinning
     another tenant's conversation returns 404. Backend tests cover this.
  4. *(sc-155)* After the first complete assistant reply in a conversation that still
     has the default name (the first-message excerpt or "New chat"), the server
     generates a short title (at most 60 characters, plain text, no quotes or
     markdown) from the first exchange, with a lightweight model through the existing
     retry and rate-limit helpers. It imports them and doesn't edit them.
  5. *(sc-155)* Title generation runs off the chat path. It never delays or blocks the
     reply stream, and it happens at most once per conversation. If it fails or hits a
     429, the current first-message title stays. Nothing errors to the user.
  6. *(sc-155)* A conversation created with an explicit title (raid investigations,
     recent-raid kickoffs) keeps it.
  7. *(sc-155)* The sidebar shows the new title without a manual reload (WS event or
     list refetch).
  8. Backend tests cover generation, the once-only rule, the explicit-title rule and
     the failure fallback, with the model faked.

## Phasing (from the plan's sequencing rules)

Spec, clarify, plan and tasks cover **all three stories now**, but implementation runs
in two phases:

- **Phase 1, now, in parallel with 018:** sc-154 and sc-165, using only files that don't
  reference `wcl_agent`.
- **Phase 2, after 018 merges:** sc-155, plus every file 018 holds until then
  (`backend/app/schemas.py`, `backend/app/api/ws.py`, `backend/app/agent_runner.py`). I'll
  tell you when 018 has merged. You then rebase on the sprint tip (or reset and
  cherry-pick, whichever is cleaner), re-index GitNexus in your worktree, and I grant
  the phase 2 files.

## Tentative footprint (becomes a grant after `/speckit-plan`)

Phase 1 (free now):
- `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx`, `frontend/src/types.ts`,
  `frontend/src/api/restClient.ts`, plus any new frontend component and the shadcn
  `frontend/src/components/ui/*` items you add (list them).
- `backend/app/api/conversations.py`, `backend/app/db/models.py` (`Conversation`),
  `backend/app/db/repository.py`.
- Migration `backend/migrations/versions/0012_<name>.py` with
  `down_revision = "0011_guide_content_types"`. **You hold the 0012 slot.** F3 takes 0013
  after you.
- New backend test files, for example `backend/tests/test_conversation_pinning.py`.
  Existing test files that reference `wcl_agent` (`test_tenant_isolation.py`,
  etc.) are held by 018 until it merges, so put new tests in
  new files.

Phase 2 (after 018 merges):
- `backend/app/schemas.py` (`ConversationOut`, a new update body), which 018 holds
  because of its `wcl_agent.constants` import. **This matters for sc-165:** the
  `pinned_at` field and a `PATCH` request schema live here. Plan around it: build the
  DB, repository, frontend and API wiring in phase 1, and add the schema fields in
  phase 2. Alternatively, if 018 has merged by the time you reach those tasks, it is
  simply granted then. Tell me in your file list which you prefer.
- `backend/app/api/ws.py` or `backend/app/agent_runner.py` (the sc-155 turn-completion
  hook; keep it small). After you, F4 (sc-164) gets both files.
- A small title service under `backend/app/services/` (new file, free now if you want
  to start it early, as long as it doesn't edit `wcl_agent`).
- Rules: `wcl_agent` `model_retry` and the model helpers belong to F4. You **import**
  them for sc-155 and must not edit them. If you need a change there, ask me first.
- **Not yours:** `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/*`, and `MessageList.tsx`,
  `StreamMarkdown.tsx` and `pdf_report.py` (no feature touches those).
- Frontend dependency changes (`frontend/package*.json`) need the token. Ask first;
  shadcn adds may need it.

## Notes from the scrum master

- The UI goes through the shadcn MCP (constitution VII): search the registry for the pin
  toggle, the "Pinned" group and any menu or dropdown on the sidebar entry, then run the
  audit checklist. Icons come from `react-icons` only.
- Tenancy: the pin API must go through the existing tenant-scoped session/RLS path, and a
  test must show that another tenant's conversation gives 404 (AC 3). Run GitNexus
  `impact` on the repository functions you change (title logic around line 130).
- sc-155: say in the plan how the background task is owned (the existing
  `services/background.py` pattern?), how "at most once" is enforced (a DB condition,
  not in-memory), and how the sidebar learns the new title (AC 7).
- Before hand-off, re-index **your worktree** and run `detect-changes`. Restore
  `CLAUDE.md` and `.specify/feature.json` before every commit.
