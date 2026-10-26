# Brief 030 — Participant resolution tool

- **Feature:** 030 · **Branch:** `030-participant-resolution` (set `GIT_BRANCH_NAME=030-participant-resolution` for `/speckit-specify`; spec dir `specs/030-participant-resolution/`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (track B). Before you start, the scrum master resets it to the sprint tip.
- **Base ref:** `sprint-2026-10-26` `1da8bca` (027 + 028 merged, plus the sprint artefacts)
- **Story:** sc-206 (3) Agent resolves run/raid participants with class and role for profile actions.
- **Peer:** track A developer on 029 (`dev-a-029`).
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-26/plan.md` (section 030 + the overlap table), decisions `.../decisions.md` (D5 and D9 binding), ownership `.../ownership.md`.
- **Design (the agreed input; cite it, don't re-derive it):**
  `documentation/designs/self-aware-agent/participants-and-confirmation.html` (`#resolution`,
  `#participants`, `#filters`, `#files`, `#tests`); the proposal contract in `capabilities-and-tools.html#proposal-contract`.

## OWNER GATE (decision D7), hard rule

Run `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → checkpoint.
**Do NOT run `/speckit-implement` and do NOT change any code** until the scrum master relays
the owner's thumbs up as an explicit "GO implement 030".

## Acceptance criteria (verbatim from plan.md)

1. Given a report (and a fight or run, where relevant), the agent can get the
   participants with name, realm, region, class, spec and role, in a compact output
   (the size budget set in the design). Pets and NPCs are excluded.
2. Run resolution follows the design and decision D5: use the run in the chat context
   when there is one; when there are several candidates and the user didn't say
   "last"/"latest", Barnaby asks which one rather than guessing.
3. Data comes through the single WCL client (Redis cache and raw-fetch persistence),
   reusing the existing queries and report tools where they cover the need. No
   duplicate GraphQL query (constitution I).
4. Filters like "except the shaman" and "only the healers" can be applied to the
   structured output (each participant carries class and role); a test covers both
   examples on faked data.
5. Tests with faked WCL responses cover a raid and an M+ run, an unknown realm, and
   the ambiguous-run case.

## Design decisions already made (don't reopen them)

- New slim tool `get_report_participants(report_code, fight_id=0)` in `wcl_agent/tools/participants.py`,
  built on the existing `_report_fields` helper in `wcl_agent/tools/report_tools.py`. No new GraphQL
  query and no new cache family. Size budget to assert: ≤120 chars/row, M+ result ≤1,500 chars,
  40-player raid ≤6,000.
- Run resolution (D5): a report named in the message, then the one run of that kind in this chat, then the
  newest stored run only on "last"/"latest", otherwise ask with ≤5 candidates. A compact "Recent runs"
  preamble line is built in `services/profile_context.py`, with report codes on the Raids line.
- Filters are applied by the model on the structured rows (no filter arguments).
- The design's Inferred note: record a real `playerDetails` response shape first (for the fakes) before
  relying on the keys. If you can't reach WCL, say so at the plan gate.

## Footprint (tentative; becomes the grant after /speckit-plan)

Now: `wcl_agent/tools/participants.py` (new), `backend/app/services/profile_context.py`,
`backend/app/services/raids.py` (`REPORT_SCOPED_TOOLS`), `frontend/src/toolLabels.ts` +
`frontend/src/lib/spells.ts` (optional label), `backend/tests/test_participants_tool.py` (new),
`backend/tests/test_profile_context.py`, `specs/030-participant-resolution/**`.
**Only after 029 merges** (029 holds them until then): `wcl_agent/agent.py` (one registration line
plus the run-resolution guidance), `backend/app/api/ws.py` (`_build_turn_preamble`: two reads + one
kwarg), `backend/tests/test_prompt_contract.py`. Plan your tasks so these come last. You'll rebase
onto the sprint tip when the scrum master says 029 has merged.

## Product-owner build notes (acceptance D10/D11, binding)

- `get_report_participants` is a WCL tool: register it in `wcl_agent` `TOOL_GROUPS`/`TOOLS` (029 introduces
  `TOOL_GROUPS`), **not** through backend `extra_groups`.
- The "Recent runs" preamble line (`profile_context.py` + the read in `ws._build_turn_preamble`) is in scope
  (it implements D5). The `ws.py` order is 029 → 030 → 031.
- D10: the approve/cancel outcome does not enter the ADK session.

## Working rules

- GitNexus impact before every edit (`build_preamble`, `_build_turn_preamble`, `_report_fields`).
- Ports for any throwaway app or DB: app **18030**, Postgres **15430**, Redis **16330**. Use your own
  `docker run` containers, never `docker compose` or the default ports. Never read the owner's `.env`.
- Before change detection, run `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force`
  in your worktree.
- No scope creep. sc-206 only. Extras go to the scrum master as Backlog suggestions.
- Never push. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.
