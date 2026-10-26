# Brief 029 — Capability summary + profile proposal tools

- **Feature:** 029 · **Branch:** `029-agent-profile-proposals` (set `GIT_BRANCH_NAME=029-agent-profile-proposals` for `/speckit-specify`; spec dir `specs/029-agent-profile-proposals/`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (track A). Before you start, the scrum master resets it to the sprint tip.
- **Base ref:** `sprint-2026-10-26` `1da8bca` (027 + 028 merged, plus the sprint artefacts)
- **Stories:** sc-204 (2) Harness self-description in the agent's context; sc-205 (5) Agent tools to read and edit the user's profile (characters, friends, roles).
- **Peer:** track B developer on 030 (`dev-b-030`).
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-26/plan.md` (section 029 + the overlap table), decisions `.../decisions.md` (D4–D9 binding), ownership `.../ownership.md`.
- **Design (the agreed input; cite it, don't re-derive it):** `documentation/designs/self-aware-agent/capabilities-and-tools.html` (decisions C1–C14, `#proposal-contract`, `#files`, `#tests`) and `index.html`. For 031's consumption side, see `participants-and-confirmation.html`.

## OWNER GATE (decision D7), hard rule

Run `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → checkpoint.
**Do NOT run `/speckit-implement` and do NOT change any code** until the scrum master relays
the owner's thumbs up as an explicit "GO implement 029".

## Acceptance criteria (verbatim from plan.md)

1. *(sc-204)* The system prompt carries a capability summary **generated from the
   registered tools**. The hand-written tool list in `wcl_agent/agent.py` is replaced
   by it (no parallel hand-maintained list). A test shows that registering or removing
   a tool changes the summary with no prose edit.
2. *(sc-204)* The summary says what Barnaby can change (own characters and friends,
   including roles, always through a proposal the user approves) and what he can't,
   and stays within the token budget set in the 027 design (asserted in a test).
3. *(sc-205)* The agent can read the current user's profile and propose adding,
   updating and removing own characters and friends (including roles), in bulk. The
   tools **never write**: they return a change proposal in the 027 contract's shape,
   with a per-item validation result (realm/region, duplicates, limits, already a
   friend).
4. *(sc-205)* Executing an approved proposal goes through **one** shared profile service,
   which the REST endpoints in `backend/app/api/profile.py` also use. The existing
   profile API tests pass unchanged.
5. *(sc-205)* A proposal is bound to its tenant and user. Executing another tenant's or
   user's proposal fails as not found, an expired proposal can't be executed, and a
   second execution of the same proposal changes nothing (idempotent). Each case has
   a backend test.
6. *(sc-205)* Names and realms that come from WCL data are validated by the same rules
   as manual entry before they enter a proposal (prompt-injection guard from the
   design). Test with a hostile character name.
7. If proposals are stored in Postgres: migration `0016` upgrades and downgrades
   cleanly and the table has the same tenant RLS policy as the other tenant tables.
8. The full backend suite passes, with no new failures against base `cf370e8`.

## Decisions already made (in the design; don't reopen them)

- D8: `MAX_FRIENDS = 50`, enforced only in `repository.add_character`. Profiles already over 50
  keep all their friends; only new adds are refused. `friend_limit` is the code for both the REST 409
  and the proposal validation, and `CharactersTab.tsx` shows a readable message.
- D9: `raid_role` on add is null by default and set only when the user asks. `played_role` is
  display only and never stored.
- Contract v2: `message_seq` (nullable, also on the wire), `list_proposals(identity,
  conversation_id)`, a realm-slug comparison in the shared `repo.find_character_identity`, and more
  than 30 items is a tool error.
- No WebSocket frames in 029. The only `ws.py` change is the one line in `_handle_turn` that sets
  `current_identity`. 031 owns the frames, the REST approve/cancel routes and the `message_seq`
  assignment.

## Footprint (tentative; becomes the grant after /speckit-plan)

From the design's `#files` section: `wcl_agent/capabilities.py` (new), `wcl_agent/agent.py`,
`wcl_agent/tools/tools.py` + `wcl_agent/tools/report_tools.py` (docstrings only),
`backend/app/agent_runner.py`, `backend/app/agent_tools/{__init__,profile_tools}.py` (new),
`backend/app/services/profile_service.py` (new), `backend/app/services/profile_proposals.py` (new),
`backend/app/api/profile.py`, `backend/app/api/ws.py` (**one line only**),
`backend/app/tenancy/context.py`, `backend/app/schemas.py`, `backend/app/db/models.py`,
`backend/app/db/repository.py` (or a new `backend/app/repositories/profile_proposals.py`),
`backend/migrations/versions/0016_profile_proposals.py` (new; **revision `0016_profile_proposals`,
down_revision `"0015_rescan_mplus_runs"`**), `frontend/src/components/profile/CharactersTab.tsx`
(friend_limit message only), `backend/tests/test_{capabilities,profile_proposals,profile_tools}.py`
(new), `backend/tests/test_prompt_contract.py`, `specs/029-agent-profile-proposals/**`.
After `/speckit-plan`, send the exact list; anything not on it needs a grant.
Shared later: 030 adds one registration line to `wcl_agent/agent.py`, edits `ws.py` and
`test_prompt_contract.py` **after you merge**. 031 extends `schemas.py`, `ws.py` and
`CharactersTab.tsx` after you merge. Keep your edits there minimal.

## Product-owner build notes (acceptance D10/D11, binding)

- 030's `get_report_participants` is a WCL tool and registers in `wcl_agent` `TOOL_GROUPS`/`TOOLS`.
  `extra_groups` is only for backend-side tools such as the profile tool (C6's "the same way" wording is loose).
- Part 1's open questions take the recommended option: identity rules apply to proposals only; syntax and
  duplicate checks only, with no WCL existence lookup; older pending proposals stay valid until they expire.
- D10: the approve/cancel outcome does **not** enter the ADK session. The next turn's preamble carries the real profile.
- The live agent-eval cases in part 1's Tests are optional. The **offline scripted agent test is required**.

## Working rules

- GitNexus impact before every edit. Expect HIGH on `build_agent`, `build_instruction` and the
  `profile.py` helpers; report it in the plan.
- Ports for any throwaway app or DB: app **18029**, Postgres **15429**, Redis **16329**. Use your own
  `docker run` containers (never `docker compose`, never the default ports). Never read the owner's
  `.env`; boot with dummy credentials. The RLS and migration tests need real Postgres.
- Before change detection, run `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force`
  in your worktree.
- Baseline first: run `uv run --extra test pytest -q` on the base and record the counts in the checkpoint.
- No scope creep. sc-204 + sc-205 only. Extras go to the scrum master as Backlog suggestions.
- Never push. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.
