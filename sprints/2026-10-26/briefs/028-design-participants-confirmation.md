# Brief 028 — Design doc part 2: participant resolution and in-chat confirmation

- **Feature:** 028 · **Branch:** `028-design-participants-confirmation` (create it yourself:
  `git -C /home/rudolf/dev/wcl-worktrees/dev-b checkout -b 028-design-participants-confirmation`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (track B)
- **Base ref:** `sprint-2026-10-26` @ `cf370e8`
- **Story:** sc-212 (3 pts), Design doc (HTML): self-aware agent, participant resolution
  and in-chat confirmation flow (for the build stories sc-206, sc-207). Read the full story on
  Shortcut (`mcp__shortcut__stories-get-by-id` 212). It lists the design questions and the top nav.
- **Peer:** track A developer on 027 (`dev-a-027`). It owns
  `documentation/designs/self-aware-agent/index.html` and the **proposal-contract table**
  in `capabilities-and-tools.html`.
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-26/plan.md`
  (section 028 and the overlap table), decisions `.../decisions.md` (D4–D6 binding),
  ownership `.../ownership.md`.

## Process (doc-only, decision D3)

No Spec Kit run. Flow:
1. Move sc-212 to **In Progress** (iteration 161 is set already).
2. Explore the real code with GitNexus: the WCL tools in `wcl_agent/`
   (`get_report_player_details`, `get_report_master_data`), the single WCL client and cache,
   `backend/app/api/ws.py` (the existing stream frames), `frontend/src/types.ts`,
   `frontend/src/components/MessageList.tsx`, the profile page and sidebar friend lists, and
   `documentation/architecture/*.html`.
3. Start with the participant-resolution half. Don't define the proposal shape. 027 sends
   the contract table early (relayed by the scrum master), and you link to it. A mismatch is
   listed as an Open question.
4. Send the scrum master an outline or table of contents when you're about halfway through. That's
   the one review checkpoint.
5. Hand-off: commit on your branch (never push), then send the scrum master the branch, commits,
   files changed, and an AC 1–7 mapping (section anchors), plus how you checked
   "no network requests" and 390px.

## Acceptance criteria (verbatim from plan.md)

1. Every design question in sc-212 has a decision or an explicit "Open question" with
   options: run resolution from chat context and the ambiguous case; which existing
   WCL tools and cached data give name, realm, class, spec and role
   (`get_report_player_details`, `get_report_master_data` in `wcl_agent`) and whether a
   new tool or a slimmer output is needed; how filters like "except the shaman" or "only
   the healers" are applied; the confirmation card; the WebSocket frames or REST call
   that carry the proposal and the approval (extending `backend/app/api/ws.py` and the
   frontend types); what the agent says after approve or cancel; how the profile page
   and friend lists refresh without a reload; and the tests (component, WS protocol,
   end-to-end happy path).
2. It uses 027's proposal shape by linking to its table. Any mismatch is listed as an
   open question, not redefined.
3. Edge cases each have a stated behaviour: an expired proposal, a reload
   mid-confirmation, two tabs, an approval after the conversation moved on, a character
   already a friend, a cross-realm or unknown realm.
4. UI parts name the shadcn registry items to use (found through the shadcn MCP,
   constitution VII), or say why a part is hand-built.
5. Decisions cite sources and label inferences, as in 027 AC 4.
6. Diagrams: the sequence "user request → resolve run → participants → filter →
   proposal → card → approve → refresh", a decision flow for ambiguous run resolution,
   and a wireframe-style SVG of the confirmation card. Same SVG and page conventions as
   027 AC 5–6.
7. It follows the product decisions in `decisions.md` (D4–D6).

## Design constraints the scrum master adds (from the plan's overlap table)

- 031 owns the new proposal and approval frames (ws.py, types.ts). They call 027/029's shared
  service function (e.g. `execute_proposal`) and never write profile data themselves.
- 030's tool lives in its own module under `wcl_agent/tools/` and needs only a one-line
  registration in `wcl_agent/agent.py`. Design it that way and reuse existing queries
  (constitution I). Set a numeric output-size budget that 030 can assert.
- No scope creep: design only what sc-206 and sc-207 need. sc-208 (bubble width) needs no
  design. Extras go in "Open questions / follow-ups".
- **shadcn MCP quirk:** it reports "no configured registries". Pass
  `registries: ["@shadcn"]` explicitly to search and view calls.

## Footprint (tentative grant)

- `documentation/designs/self-aware-agent/participants-and-confirmation.html`

Nothing else. Don't touch `index.html` (owned by 027). No code changes. Don't commit
`CLAUDE.md` or `.specify/feature.json`. No app, DB or ports are needed.
