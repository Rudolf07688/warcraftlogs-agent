# Sprint 2026-10-26 decisions (product owner)

## D1 — 2026-10-26: Sprint scope
- **Question:** What does this sprint deliver?
- **Answer:** Epic 203 (self-aware agent) end to end: design docs sc-211, sc-212, then
  sc-204, sc-205, sc-206, sc-207, plus sc-208 (chat bubble width) bundled with sc-207.
  20 points in features 027–031.
- **Why:** The owner's newest tickets (created today) are the epic-203 design docs; the
  four build stories are blocked only by them; finishing one epic gives a complete,
  testable capability. Epic 103 (sc-178 + sc-129) heads the next sprint.

## D2 — 2026-10-26: Who accepts the design docs before the build starts
- **Question:** sc-211/212 say the build stories are built "against an agreed design".
  May the build (029–031) start once the PO accepts the docs?
- **Answer:** Yes. The PO reviews 027/028 against their acceptance criteria and accepts
  them as the build gate. The owner still sees both docs at Under Review and can request
  changes as follow-ups.
- **Owner confirmed (2026-10-26, via team-lead):** the owner wants epic 203 this sprint. Go
  with the recommended plan, not Plan B. The PO accepts sc-211/sc-212 against their ACs,
  and sc-204..207 plus sc-208 run this sprint. Plan B is retired.
- **Why:** Keeps the sprint on its goal without idling two tracks, while leaving the final
  say with the owner.

## D3 — 2026-10-26: Process for doc-only features
- **Question:** Do 027/028 run the Spec Kit flow?
- **Answer:** No. They are doc-only (like 026, the architecture docs). Their HTML is the
  design input to 029–031, whose Spec Kit runs cite the design instead of re-deriving it.
- **Why:** A spec for a design doc would duplicate it (constitution I, III).

## D4 — 2026-10-26: Confirmation granularity (product rule for 027/028/031)
- **Question:** Partial approval of a proposal, or all-or-nothing?
- **Answer:** v1 is **Approve all valid items / Cancel**. Items that fail validation are
  shown on the card, marked as skipped, and never applied. No per-item toggles in v1;
  the designs may list per-item selection as an open question / follow-up.
- **Why:** Simplest flow that still never writes anything the user didn't see (YAGNI).

## D5 — 2026-10-26: Ambiguous "the dungeon / the raid" (product rule for 028/030)
- **Question:** When the run is ambiguous, does Barnaby ask or pick the most recent?
- **Answer:** Use the run already in the chat context (current report or last discussed
  run). If there is none, or several candidates, Barnaby asks which one, listing the
  candidates briefly. He picks the most recent only when the user says "last", "latest"
  or similar. Never guess silently.
- **Why:** A wrong guess writes the wrong people into the profile; one extra question is
  cheap.

## D6 — 2026-10-26: Every agent write needs approval
- **Question:** Do removals and role changes also need the card, or only adds?
- **Answer:** All agent-initiated profile changes (add, update, remove, own characters
  and friends) go through a proposal and the card. The agent never writes directly.
- **Why:** sc-207's promise is "the agent never silently changes my data".

## D7 — 2026-10-26: Owner plan-review gate before implementation (updates D2)
- **Question (owner, via team-lead):** When does the owner see the plan for the builds?
- **Answer:** 027/028 continue, and the PO still accepts both design docs. Before 029–031
  start **implementing**, the PO ends a turn with `ESCALATION: OWNER PLAN REVIEW`. It
  covers the end-to-end flow, the features 029–031 with their stories and tracks, the key
  design decisions (proposal format, security model, participant resolution,
  confirmation card), the risks, and the paths of the design docs. No implementation in
  029–031 until the owner's thumbs up is relayed. Spec/plan drafting for 029–031 may
  proceed meanwhile. After the thumbs up, there are no more owner gates this sprint;
  the PO decides everything except genuinely irreversible actions.
- **Why:** The owner wants one look at the overall plan before code is written, then
  wants the team to run on its own.

## D8 — 2026-10-26: Friend cap (027 / sc-211 question, built in 029)
- **Question:** sc-211 asks for a "max friends" limit, but none exists (only
  `MAX_OWN_CHARACTERS = 10` in `backend/app/db/repository.py`). (A) No cap, with only the
  30-items-per-proposal bulk cap; or (B) `MAX_FRIENDS = 50` in `repository.add_character`,
  the shared write path, so REST adds are capped too (error code `friend_limit`)?
- **Answer:** (B), with the cap at 50 and enforced in the single shared write path. Profiles
  already over 50 keep every friend; only new adds are refused. The REST error and the
  proposal's per-item validation both report `friend_limit`, and the profile page shows it
  as a readable message, not a generic failure.
- **Why:** Each friend costs tokens on every model request (the KNOWN PLAYER CONTEXT
  preamble) and starts a background guide task, so unbounded bulk adds through the agent
  have a real cost. One cap in one place (constitution I) keeps REST and agent writes
  consistent.

## D9 — 2026-10-26: raid_role for friends added from a run (028 OQ-4)
- **Question:** When Barnaby adds friends from a run, is the role they played stored as an
  explicit `raid_role` override (B), or left empty so it's inferred from the spec, as for
  manual adds (A)?
- **Answer:** (A) by default. `raid_role` stays empty, and the card shows the role played
  in that run for information only. Barnaby sets an explicit role only when the user asks
  for one (e.g. "add them as healers"), because sc-205 covers roles.
- **Why:** One run is weak evidence (people flex), an override sticks until the user
  changes it, and A matches manual adds.
- **Noted (SM technical decisions, accepted):** 031 adds vitest + @testing-library/react
  + jsdom as dev dependencies for its component test, with a Complexity Tracking entry
  (constitution III). The approval goes over REST
  (`POST /api/profile/proposals/{id}/approve|cancel`) and the proposal reaches the browser
  as a WS frame. Both call only 029's service.

## D10 — 2026-10-26: Does the approve/cancel outcome enter the ADK session? (028 OQ-2)
- **Answer:** No (option a). The next turn's KNOWN PLAYER CONTEXT preamble carries the real
  profile, and the server-built follow-up line is saved as a chat message only.
- **Why:** There's one source of truth (the profile tables), no synthetic events, and
  nothing to keep in sync (constitution I, III).

## D11 — 2026-10-26: 027 and 028 accepted; notes for the builds
- **Answer:** ACCEPT both design docs (027 at a696bcf, 028 at bc46d29) as the build gate for 029–031 (D2). The PO checked:
  the diffs touch only the granted files, there are no external references, and these
  citations exist on base cf370e8: ws.py:265 `set_refresh_actor`,
  repository.py:1013 `MAX_OWN_CHARACTERS`, report_tools.py `_report_fields`/`_fight_ids`,
  datasheet.py `_player_details`, App.tsx:319 maps only `detail.messages`,
  `find_character_identity` compares `lower(server)`.
- **Build notes (no rework of the docs):**
  1. 030's participant tool is a WCL tool. It registers in `wcl_agent` `TOOL_GROUPS`/`TOOLS`
     (part 2), **not** through the backend `extra_groups` (part 1 C6 says "the same
     way"; part 2 is right). `extra_groups` is only for backend-side tools.
  2. 030's "Recent runs" preamble line (`profile_context.py` + the read in
     `_build_turn_preamble`) is in scope: it is how D5's "ask with candidates" works.
     ws.py order: 029 → 030 → 031.
  3. Part 1's open questions take the recommended option: identity rules for proposals
     only (A), syntax and duplicate checks only, no WCL existence lookup (A), and older
     pending proposals stay valid until they expire (A).
  4. The live agent-eval cases (part 1, Tests) are optional; the offline scripted test
     is required.
- **Follow-ups filed (Backlog):** sc-213 (bug, 2) charts not restored when a chat is
  reopened; sc-214 (feature, 2, epic 203) per-item selection on the card (OQ-1 / D4).

## D12 — 2026-10-26: Owner thumbs up; D7 gate cleared
- **Answer (owner, via team-lead, after the ~18:50 pause/resume):** the owner is "more than happy
  with the plan". 029–031 may implement. No owner gates remain this sprint; the PO decides
  everything and escalates only genuinely irreversible actions.
- **WCL participant data:** no live recording of `playerDetails`. 030 builds on the
  inferred fixtures from the 028 design (field names as documented there) and keeps the
  parser tolerant of missing keys (missing realm → `realm: null`, as designed). The owner
  verifies against a real report at Under Review. This replaces the design's "record one real
  response first" step.

## D13 — 2026-10-26: App features in the capability summary (029 / sc-204)
- **Question:** Should the generated summary also carry a fixed line naming the app's user-facing
  features (profile page, Raids page, class guides, PDF export, chat filters), or only the tool
  lines and the can/cannot lines?
- **Answer:** (B) Add one fixed line of app facts, with no tool names, inside the 4,000-character
  budget. It lists **only features that exist on the base**. There's no per-chat *character*
  filter yet (epic 107 / sc-144 isn't built), so the line names the boss/encounter
  checkboxes (EncounterPicker) instead, and doesn't mention a character filter.
- **Why:** sc-204's story text lists these features, so it's in scope. A line that names an
  unbuilt feature would make Barnaby promise something the app can't do.

## D14 — 2026-10-26: 030 (sc-206) accepted
- **Answer:** ACCEPT at deecaab. The PO re-ran the backend suite in dev-b (1083 passed, 3 skipped,
  1 deselected) and read `wcl_agent/tools/participants.py` and the shared-file diffs (ws.py: 2 reads
  + 2 kwargs; agent.py: import, TOOLS entry, one tool-list line, `<RUN_RESOLUTION>`). AC 1–5 met.
  The hand-written tool-list line is temporary: 029's generated summary replaces it, and 029's
  rebase must carry `get_report_participants` into `TOOL_GROUPS` (checked at 029 acceptance).
- **Owner live check (Under Review):** "who was in <report>" against a real report (the fixtures
  are Inferred, D12), and the full example request once 029 and 031 are in.

## D15 — 2026-10-26: Duplicate "naive timestamp as UTC" helper (029)
- **Question:** 029's `profile_proposals.py` needs the `_aware(dt)` logic that already exists in
  five places on base (guide.py, invitation_service.py, auth/sessions.py, and inline in
  password_reset_service.py and admin_users.py). File a chore, or fix it now?
- **Answer:** Both, split. 029 must not add a sixth copy: it adds **one** small shared helper (its
  choice of module, e.g. `backend/app/db/` or a `timeutil` module) and uses it in its own new code.
  Moving the five existing copies onto it is a Backlog chore, sc-216 (1 pt, Low), because those
  files are outside 029's footprint and the change is unrelated to sc-205.
- **Why:** New code follows constitution I without widening 029's scope.

## D16 — 2026-10-26: 029 (sc-204 + sc-205) accepted
- **Answer:** ACCEPT at c28d1ef (code ends at ca6cdf1). The PO re-ran the backend suite in dev-a
  (1152 passed, 6 skipped, 1 deselected) and read: `agent_tools/profile_tools.py` (identity from
  `current_identity` + session, fails closed on a mismatch or non-UUID session), the
  `repositories/profile_proposals.py` queries (tenant **and** user in every WHERE, FOR UPDATE on
  execute/cancel), `execute_proposal`/`cancel_proposal` (single transaction, idempotent, guides
  scheduled after commit), the repository friend cap (D8) and slug identity (C12, the SQL mirrors
  `server_slug`), and the ws.py/agent_runner.py edits. AC 1–8 are met. 030's tool is in the "Report deep-dive"
  group and the temporary hand-written line is gone (D14 check).
- **Accepted deviations:** no `schedule_guides` wrapper; the realm regex allows parentheses; the
  `friend_limit` message has no number.
- **Owner live checks (Under Review):** (a) the shared runner also serves greeting, guide and
  guild-summary runs: check that the profile/"can change" lines don't leak into generated guide or
  summary text (fallback: register the profile group for chat only); (b) "make <friend> a healer"
  and "remove <friend>" produce a correct card once 031 is in.

## D17 — 2026-10-26: 031 AC 6 at 390px (sc-208)
- **Question:** At 390px the page overflows to 698px both before and after 031, because the app has
  no mobile layout (fixed 260px sidebar, chat header controls). (A) Accept AC 6 at bubble level
  for 390px; (B) add a minimal narrow-screen layout in 031; (C) clip with overflow-x: hidden?
- **Answer:** (A). At 390px, AC 6 holds if bubbles never exceed their column, wide content scrolls
  inside the bubble, and the page width doesn't grow compared with base (698px before and
  after). 1280px and 1920px must have no page overflow at all (measured: none). The header and
  sidebar overflow stays with sc-175 (mobile layout); a comment with the measurements was added there.
- **Why:** The overflow predates this sprint and comes from the layout shell, not the bubbles. (B) is
  scope creep into sc-175, and (C) hides controls. The AC wording in plan.md was too broad for a
  bubble story; this is the PO's clarification of the PO's own AC.

## D18 — 2026-10-26: 031 (sc-207 + sc-208) accepted
- **Answer:** ACCEPT at 87c17d8. The PO re-ran everything in dev-b: backend 1171 passed, 6 skipped,
  1 deselected; `npm test` 12 passed; `npm run build` clean. Read `api/proposals.py` (CSRF-authenticated,
  service-only, follow-up saved only on the call that leaves `pending`, invalid names never echoed,
  Markdown escaped), the ws.py proposal frame (built from the stored row, scoped to the user), and
  ProposalCard (no `dangerouslySetInnerHTML`/StreamMarkdown). package.json adds only 4 dev deps + a
  `test` script. AC 1–7 are met, AC 6 per D17.
- **Accepted deviations:** Cancel uses the `secondary` button variant; the follow-up is saved in its own
  short tenant_scope; ClassAvatar lives in its own module. At 390px the card's content overflows its
  narrow bubble (no page widening); same root cause as sc-175.
- **Owner live checks (Under Review):** the first real-model run of the example request, the two-tab
  refresh, and that live WCL `playerDetails` keys match the inferred fixtures (D12).
- **sc-213 note:** comment added (the reload mapping already attaches artifacts; look at the figure
  rebuild or PlotlyArtifact).
