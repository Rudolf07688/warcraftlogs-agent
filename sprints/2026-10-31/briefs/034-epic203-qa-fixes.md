# Brief 034 — Crucial epic-203 QA fixes

- **Feature:** 034 · **Branch:** `034-epic203-qa-fixes` (set `GIT_BRANCH_NAME=034-epic203-qa-fixes` for `/speckit-specify`; spec dir `specs/034-epic203-qa-fixes/`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (track B), detached at the base. Deps synced.
- **Base ref:** `sprint-2026-10-31` @ `b963463`
- **Stories (all `qa-deferred`, crucial):** sc-241 (2) one invalid proposal item crashes the profile tool and the turn; sc-242 (2) overlapping approvals post the follow-up twice or return 500; sc-243 (2) proposal card shows in the wrong chat after a mid-turn switch, plus the misleading tool status. Read each ticket in Shortcut: its fix suggestion is the starting point. Move them to **In Progress** when you start.
- **Peer:** track A developer `dev-a-032` (LLM provider switch; no file overlap with you).
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/plan.md` (section 034 and the overlap table), decisions `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/decisions.md`, ownership `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/ownership.md`. Prior context: `sprints/2026-10-26/qa-triage.md`, `specs/029-agent-profile-proposals/`, `specs/031-confirmation-card/`.

## OWNER GATE (binding)

You may run `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` and write `checkpoint.md`.
**No `/speckit-implement` and no code** until the scrum master relays the owner's thumbs-up ("OWNER GO").

## Acceptance criteria (verbatim from plan.md)

1. *(sc-241)* Raw item dicts through the real ADK argument path
   (`FunctionTool.run_async`): realm `None`, `played_role` "Healer" and one valid item
   produce a stored proposal with 2 skipped rows (with the right codes:
   `invalid_realm` / `invalid_region` for blank or missing realm/region) and 1 valid row.
   Roles compare case-insensitively. No `agent_error` with raw Python text.
2. *(sc-241)* An unexpected exception inside the tool returns `{"status": "error"}`
   with a plain message, and the turn continues.
3. *(sc-242)* Two overlapping approvals (simulated in a test) apply the change once,
   save exactly one follow-up line and return no 500. Only the call that made the
   transition (decided under `FOR UPDATE`) saves the follow-up, in the same
   transaction. The same holds for cancel.
4. *(sc-243)* A proposal card (or loose card) attaches only to the chat whose turn
   produced it, keyed by the turn's conversation id from the `meta` frame. Switching
   chats or starting a new chat mid-turn never shows it in the wrong chat, and reopening
   the original chat shows it.
5. *(sc-243)* While `propose_profile_changes` runs, the status reads "Preparing profile
   changes" (or similar) with a matching spell entry, not "Searching Warcraft Logs".
6. The existing proposal, card and WS tests pass. Backend suite: no new failures.
   Frontend build, typecheck and tests pass.

## Footprint (tentative; becomes the grant after /speckit-plan)

`backend/app/agent_tools/profile_tools.py`, `backend/app/services/profile_proposals.py`,
`backend/app/schemas.py` (`ProfileChangeIn` only; 033 later adds `ModelsResponse.provider` — different class),
`backend/app/api/proposals.py`, `backend/app/db/repository.py` (only if the follow-up insert moves
into the locked transaction), `frontend/src/App.tsx`, `frontend/src/toolLabels.ts`,
`frontend/src/lib/spells.ts`, tests, `specs/034-epic203-qa-fixes/**`.
If you need `frontend/src/api/wsClient.ts`, `backend/app/api/ws.py` or anything else, ask first.

**Not yours:** anything under `wcl_agent/llm/`, `wcl_agent/agent.py`, `config.py`, `main.py` (032/033).
No migration is expected; if you need one, ask (revision `0017`, down `0016_profile_proposals`).

## Working rules

- GitNexus impact before every edit (`propose_profile_changes`, `execute`/`cancel` in the proposal
  service, the approve/cancel routes, the App.tsx frame handlers); flag HIGH/CRITICAL.
- Run `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force` in your worktree first.
- Ports for any throwaway app or DB: app **18034**, Postgres **15434**, Redis **16334**. Your own
  `docker run` containers only (never `docker compose` or the default ports). The sc-242 race test
  should run against a real Postgres (`FOR UPDATE` semantics), on your port.
- Never read the owner's `.env`; no live LLM/WCL calls. Fakes only.
- shadcn MCP (if any UI part is needed): pass `registries: ["@shadcn"]` explicitly.
- Sub-agents: send the split (tasks → exact files → model/effort) to the scrum master first.
- No scope creep: sc-241/242/243 only (sc-214, sc-219, sc-225 are separate backlog tickets). Extras go to the scrum master as Backlog suggestions.
- Reply "ACK <thing>" to each grant/decision. Never push. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.
