# Sprint 2026-10-26 plan

Product owner: `product-owner`. Sprint branch: `sprint-2026-10-26` (base `cf370e8`).
Point target 21 (19–23). **Planned: 20 points** in 5 features (027–031).
Next Alembic revision: `0016` (head `0015_rescan_mplus_runs`).

## Sprint goal

Make Barnaby a **self-aware agent** (epic 203), end to end: he knows what the app around
him can do, and the owner's example works in chat:

> "Add the characters from the dungeon to my friends, except the shaman."

Barnaby works out which run is meant and who was in it, proposes the exact profile change,
the user approves it on a card in the chat, and the profile updates without a reload.
The owner asked for the two feature design docs today (sc-211, sc-212), so they come
first, and the four build stories (sc-204..207) are built against them. Chat bubbles
that scale with the screen (sc-208) ride along with the chat-card work, because they
touch the same chat rendering files.

Why this and not epic 103 next (sc-129 DB-first reads): the owner's newest tickets and
todo.md lines are all epic 203; the four build stories are blocked only by the design docs;
and finishing one epic gives the owner a complete, testable capability. Epic 103 heads
the next sprint (see the ranked backlog, #8–#9), with sc-178 pulled forward as its gate.

## Tracks at a glance

| Order | Track A (agent + backend) | Track B (WCL tools + chat UI) |
|---|---|---|
| 1st (parallel) | **027** Design part 1: capabilities and profile write tools (sc-211, 3) | **028** Design part 2: participants and in-chat confirmation (sc-212, 3) |
| 2nd | **029** Capability summary + profile proposal tools (sc-204 + sc-205, 7), after 027 + 028 accepted | **030** Participant resolution tool (sc-206, 3), after 028 accepted |
| 3rd | (free: help review / QA prep) | **031** Confirmation card, profile refresh, bubble width (sc-207 + sc-208, 4), after 030; its approve wiring after 029 merges |
| Total | 10 | 10 |

The critical path is 027 → 029 → 031's approve wiring. 031 may start its card UI and
sc-208 against the 027 proposal contract (with a fake proposal) before 029 merges, and
wire the real approve call once 029 is in the sprint branch.

### Same-file overlaps: one owner at a time

| Shared files | Features | Rule |
|---|---|---|
| `documentation/designs/self-aware-agent/index.html` | 027 vs 028 | 027 owns it. 028 only links to it. |
| Proposal contract (shape of a change proposal) | 027 vs 028 | 027 writes it once, as a table, and shares it **early** (via the scrum master) so 028 can use it. Any mismatch is an open question in 028, never a second definition. |
| `wcl_agent/agent.py` (`build_instruction`, `build_agent` tool list) | 029 vs 030 | 029 owns it (sc-204 rewrites the hand-written tool list near line 132 into a generated summary). 030 builds its tool in its own module and adds the one-line registration **after 029 merges**, or when the scrum master grants that one edit. |
| `backend/app/api/ws.py`, `frontend/src/types.ts` (stream frames) | 029 vs 031 | 031 owns the new proposal / approval frames. 029 must not add frames; it exposes a service function that 031's transport calls. |
| `backend/app/api/profile.py` + the new shared profile service | 029 vs 031 | 029 owns both. 031 only calls the service (or the REST API) and refreshes the UI. |
| `backend/app/db/models.py`, `backend/migrations/versions/*` | 029 (`0016`, only if proposals are stored in Postgres) | Nobody else adds a migration this sprint. |
| `frontend/src/components/MessageList.tsx`, `frontend/src/styles.css` | 031 only | sc-208 and the card both live here, which is why they're one feature. |

---

## 027 — Design doc part 1: capability summary and profile write tools (Track A)

- **Stories:** sc-211 (3) Design doc (HTML): self-aware agent — capability summary and
  profile write tools (sc-204, sc-205).
- **Complexity:** low–medium (doc only, but it sets the security model).
- **Process:** doc-only feature, like 026 (architecture docs). No Spec Kit run; the
  design doc itself is the input to 029's Spec Kit run.
- **Footprint (only these files):** `documentation/designs/self-aware-agent/index.html`,
  `documentation/designs/self-aware-agent/capabilities-and-tools.html`.
- **Depends on:** nothing. **Blocks:** 029, and 028's use of the proposal shape.
- **Acceptance criteria:**
  1. Every design question in sc-211 has a decision or an explicit "Open question" with
     options: the capability summary (generated from the registered tools, injection
     point, token budget, staying correct as tools change), the profile tools (names,
     arguments, results for read / add / update / remove of own characters and friends,
     including roles), two-phase writes (proposal storage, expiry, tenant scoping,
     idempotent execution, per-item result), security (tenant scoping/RLS, own profile
     only, limits, duplicate and realm validation, prompt injection via WCL data such
     as character names), and tests (unit, integration, agent-eval).
  2. The change-proposal contract is written **once**, as a table, in this doc
     (id, items to add/update/remove with name, realm, region, class, spec, role, and a
     per-item validation result, plus status and expiry).
  3. The design reuses the existing write path in `backend/app/api/profile.py`
     (`_add` / `_patch` / `_delete` behind `add_friend`, `patch_friend`, `delete_friend`,
     `add_own_character`, …) through one shared service. There is no second write path.
  4. Each decision lists the alternatives and why, and cites real code, specs, the
     constitution or `documentation/architecture/`. Anything not grounded is labelled
     "Inferred" or "Open question". Every file and function named exists (spot-checked
     at review) or is clearly marked as new.
  5. Diagrams: the end-to-end flow for the example request (index.html), a sequence
     diagram "agent proposes → user approves → write → result", and a component diagram
     of the new tool/service pieces. Inline SVG with animated flow arrows, a pause
     control and a `prefers-reduced-motion` fallback.
  6. Page conventions: the `<style>` block copied from
     `documentation/architecture/backend-data-infra.html`; standalone HTML with **no
     network requests** (no external `src`/`href`/`@import`); light and dark themes;
     readable at 390px with no horizontal page scroll; the top nav from the story.
  7. It follows the product decisions in `decisions.md` (D4–D6).

## 028 — Design doc part 2: participant resolution and in-chat confirmation (Track B)

- **Stories:** sc-212 (3) Design doc (HTML): self-aware agent — participant resolution
  and in-chat confirmation flow (sc-206, sc-207).
- **Complexity:** low–medium (doc only).
- **Process:** doc-only feature, no Spec Kit run.
- **Footprint (only this file):**
  `documentation/designs/self-aware-agent/participants-and-confirmation.html`.
- **Depends on:** 027's proposal contract table (shared early; links to it).
  **Blocks:** 030, 031.
- **Acceptance criteria:**
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

## 029 — Capability summary + profile proposal tools (Track A)

- **Stories:** sc-204 (2) Harness self-description in the agent's context; sc-205 (5)
  Agent tools to read and edit the user's profile (characters, friends, roles).
- **Why bundled:** both change the agent definition (`wcl_agent/agent.py`), and sc-204's
  summary must describe sc-205's tools.
- **Complexity:** high (agent tools that write tenant data; security-sensitive).
- **Footprint:** `wcl_agent/agent.py` (`build_instruction`, `build_agent`), new profile
  tool module (location per the 027 design), `backend/app/api/profile.py` (refactored
  onto the shared service), a new shared profile service under `backend/app/services/`,
  `backend/app/db/models.py` + migration `0016` (only if proposals live in Postgres),
  tests under `backend/tests/`.
- **Depends on:** 027 and 028 accepted (shared proposal contract).
- **Acceptance criteria:**
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

## 030 — Participant resolution tool (Track B)

- **Stories:** sc-206 (3) Agent resolves run/raid participants with class and role for
  profile actions.
- **Complexity:** medium.
- **Footprint:** `wcl_agent/tools/` (a new or slimmed participant tool, per the 028
  design), prompt guidance for run resolution, the one-line registration in
  `wcl_agent/agent.py` (after 029 merges or by grant), tests.
- **Depends on:** 028 accepted. Its registration edit waits for 029 (see overlaps).
- **Acceptance criteria:**
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

## 031 — In-chat confirmation card, profile refresh, and bubble width (Track B)

- **Stories:** sc-207 (3) Confirm agent-initiated profile changes in chat and refresh the
  profile UI; sc-208 (1) Chat bubbles scale with screen width instead of a fixed size.
- **Why bundled:** both live in the chat message rendering (`MessageList.tsx`,
  `styles.css`); the card is rendered inside an agent bubble.
- **Complexity:** medium–high (new stream frames + UI + approval round trip).
- **Footprint:** `backend/app/api/ws.py` (proposal and approval frames, or a REST route,
  per the 028 design), `frontend/src/types.ts`, `frontend/src/api/*`, a new confirmation
  card component (shadcn parts in `frontend/src/components/ui/`),
  `frontend/src/components/MessageList.tsx`, `frontend/src/styles.css` (bubble widths
  around the fixed `min(820px…)` / `min(860px…)` rules), the profile page and sidebar
  friend-list refresh hook, tests.
- **Depends on:** 028 accepted and 030 merged. The real approve call waits for 029; the
  card and sc-208 can start against the contract with a fake proposal.
- **Acceptance criteria:**
  1. *(sc-207)* When a proposal tool returns, the browser gets the proposal (frame or
     call per the 028 design) and the chat shows a confirmation card: each item's action,
     name, realm, class/role and validation result, with **Approve** and **Cancel**.
     Built from shadcn registry parts via the MCP, audit checklist run.
  2. *(sc-207)* Approve executes the proposal through 029's service; the card then shows
     the per-item result and Barnaby posts a short follow-up line (per the design).
     Cancel writes nothing and the card shows it was cancelled.
  3. *(sc-207)* After approval, the profile page and the friend lists update without a
     page reload.
  4. *(sc-207)* Double-clicking Approve applies the change once. An expired proposal
     shows a clear "this proposal expired, ask again" state. A reload mid-confirmation
     shows the card in its real state (pending, applied, cancelled or expired).
  5. *(sc-207)* Tests: a component test of the card (pending/approved/cancelled/expired),
     a WS (or REST) protocol test for proposal → approve → result, and a backend test
     that approval goes through the shared service.
  6. *(sc-208)* User and agent bubbles take a percentage of the chat column instead of a
     fixed px width, with a sensible cap on very wide screens. At 390px, 1280px and
     1920px there's no horizontal page overflow; wide tables and code scroll inside the
     bubble.
  7. Frontend build, typecheck and tests pass; backend suite has no new failures.

### End-to-end acceptance (sprint level, checked on the merged sprint branch)

- With fakes in tests: the example request resolves a run, filters out the shaman,
  produces a proposal, renders the card, and on approve adds the friends and refreshes
  the profile.
- Live (owner, Under Review): the same request against a real report.

---

## Risks, and what to drop first

| Risk | Mitigation |
|---|---|
| The owner may want to review the design docs before anything is built on them (the tickets say "agreed design"). | Escalated to the owner (non-blocking: 027/028 start now). If the owner wants to review first, switch to **Plan B** below once the designs are done. |
| Agent tools that write user data are a new class of risk (cross-tenant writes, prompt injection via WCL character names). | Two-phase writes: tools only propose, the user approves. 029 AC 5–6 require tenant, expiry, idempotency and hostile-name tests. QA sweep includes security. |
| ADK tools need the tenant/user context to build proposals. | `agent_runner.py` already passes the tenant as the ADK `user_id`; 027 must state how tools read it. |
| 031 waits on 029 (critical path 027 → 029 → 031). | 031 builds the card and sc-208 against the contract first; only the approve wiring waits. |
| `wcl_agent/agent.py` touched by 029 and 030. | Ownership rule above; 030's registration is a one-line edit after 029 merges. |
| Live model calls may not be possible on this host (Vertex credentials). | All agent behaviour is tested with fakes; the owner checks the example request live. |

**Drop order if the sprint runs late:** (1) sc-208 out of 031 (back to Backlog);
(2) sc-206 / 030 (the agent can still propose friends the user names explicitly);
(3) the profile-refresh part of sc-207 is not droppable on its own: if 031 can't finish,
029 still ships its tested proposal service and 031 moves to the next sprint whole.
027, 028 and 029 are not dropped.

### Plan B (retired 2026-10-26: the owner chose epic 203 this sprint, decisions D2)

Keep 027 + 028 (6). Replace 029–031 (14) with epic 103's next slice and small UI work:
- **B1 (Track A):** sc-178 (2, `qa-deferred`, pulled forward as the gate) + sc-177 (3,
  `qa-deferred`, same table) + sc-129 (5) DB-first reads — 10 points.
- **B2 (Track B):** sc-208 (1) chat bubble width + sc-146 (5) deployment/hosting plan
  (doc only) — 6 points.
Plan B total: 22 points. Epic 203's build stories then lead the next sprint.

---

## Full ranked backlog (68 open stories at planning, plus sc-213..216 and QA tickets sc-219..225 and sc-241..244 filed during the sprint; sc-209/sc-210 are Under Review and excluded)

Shortcut Priority mirrors this ranking: **Highest** = this sprint, **High** = next up,
**Medium** = next sprints, **Low** = later, **Lowest** = long term and all `qa-deferred`
tickets (owner rule: QA ranks below non-QA work). One exception: sc-178 is a
`qa-deferred` ticket ranked with sc-129 because it is the design gate for it (owner's
note in the launch brief).

| # | Story | Pts | Priority | Rationale |
|---|---|---|---|---|
| 1 | sc-211 Design doc part 1: capabilities + profile tools | 3 | Highest | Gate for sc-204/205; owns the proposal contract. |
| 2 | sc-212 Design doc part 2: participants + confirmation | 3 | Highest | Gate for sc-206/207; runs alongside sc-211. |
| 3 | sc-204 Harness self-description in the agent's context | 2 | Highest | Replaces the hand-written tool list; every later agent tool is described for free. |
| 4 | sc-205 Agent profile tools (characters, friends, roles) | 5 | Highest | The core of epic 203; first agent write path, built safely once (proposals) for sc-145 and later "agent drives the app" work to reuse. |
| 5 | sc-206 Participant resolution with class and role | 3 | Highest | Makes the owner's example request work. |
| 6 | sc-207 In-chat confirmation + profile refresh | 3 | Highest | Without it nothing the agent proposes can be applied. |
| 7 | sc-208 Chat bubbles scale with screen width | 1 | Highest | Same chat rendering files as sc-207, so it's nearly free there. |
| 8 | sc-178 QA SEC-001 raw_fetches cross-tenant guard (`qa-deferred`) | 2 | High | Exception to the QA tier: the design gate for sc-129 (comment on sc-129). |
| 9 | sc-129 DB-first reads with freshness rules | 5 | High | First user-visible payoff of epic 103; heads the next sprint. |
| 10 | sc-163 Agent research playbooks | 5 | High | Big quota and latency win; uses sc-129 reads once they exist. |
| 11 | sc-197 Spec the worker server | 3 | High | Spec only. Settles the background-job architecture before sc-168, sc-201/202 and guide work pile onto the in-process `background.py`. |
| 12 | sc-146 Deployment / hosting plan | 5 | High | Doc only. Any shared deployment must first pull in sc-158. |
| 12a | sc-213 Charts not restored when a chat is reopened (bug) | 2 | Medium | Found in the 028 design. Small frontend fix, same pattern as 031's proposal reload. |
| 13 | sc-130 Normalize key WCL entities | 5 | Medium | Needs the raw fetches; the Raids page and query tools read from it. |
| 14 | sc-141 Raids page: tabs | 2 | Medium | Epic 106 as one feature (141/142/143), after sc-130. |
| 15 | sc-142 Raids page: previously pulled data | 5 | Medium | Built before sc-130 it would be rewritten against the normalized tables. |
| 16 | sc-143 Raids page: "Analyze this raid" button | 1 | Medium | Same component as sc-141/142. |
| 17 | sc-131 Agent tools to query stored data | 5 | Medium | After sc-130; sc-204's generated summary describes it automatically. |
| 18 | sc-132 Local-answer hit-rate metric | 2 | Medium | Measures sc-129/131, so after them. |
| 19 | sc-149 Agent skills for judging WoW numbers | 5 | Medium | Complements sc-163 (fetching vs judging). |
| 20 | sc-198 Worker container with NATS (JetStream) | 3 | Medium | After the sc-197 spec. |
| 21 | sc-199 Worker task state + audit trail in Postgres | 3 | Medium | After sc-198; same spec. |
| 22 | sc-200 Worker retry and dead-letter handling | 3 | Medium | Completes the worker platform before jobs move onto it. |
| 23 | sc-137 Design single-lane chat layout | 2 | Medium | Must precede sc-138; needs the owner's review of the mockup. |
| 24 | sc-138 Implement single-lane chat layout | 5 | Medium | Rebuilds the chat window; sc-207's card is a self-contained component, so it moves with little rework. Chat-window features (139, 140, 144, 118) come after. |
| 25 | sc-139 Message actions in the new layout | 2 | Medium | Part of the redesign. |
| 26 | sc-175 Mobile layout: collapsible sidebar | 3 | Medium | Do it with sc-138 so the layout shell is rebuilt once. |
| 27 | sc-140 Scroll to question on completion | 1 | Medium | In the new layout, or it gets written twice. |
| 28 | sc-144 Character filter checkboxes | 5 | Medium | Chat header, so after the redesign. |
| 29 | sc-145 (Stretch) Agent sets the character filter | 5 | Low | Needs sc-144; reuses epic 203's "agent drives the app" pattern. |
| 28a | sc-215 Bubble width caps in rem (scale with font size) | 1 | Low | Raised at 031 spec sign-off; small CSS follow-up to sc-208. |
| 29a | sc-214 Per-item selection on the profile-change card | 2 | Low | Epic 203 follow-up (D4 kept it out of v1); contract already supports it. |
| 30 | sc-201 Background job: raid and dungeon guides | 5 | Low | First job on the worker (needs sc-198..200). |
| 31 | sc-202 Background job: offline character profile | 5 | Low | Worker job; can reuse sc-205's profile service. |
| 32 | sc-166 Onboarding: new accounts to profile | 2 | Low | Epic 162 as one feature; matters once others sign up (after sc-146). |
| 33 | sc-167 Onboarding: main class/spec + content | 3 | Low | Same epic; sc-168 depends on it. |
| 34 | sc-168 Onboarding: background guide generation | 2 | Low | Best run on the worker (epic 196). |
| 35 | sc-147 Confirm browser cache usage | 2 | Low | Investigation; worth more once sc-129 settles the server-side layers. |
| 36 | sc-111 pgvector setup | 2 | Low | Epic 100 embeds stored data, so after epic 103; also gated by sc-178. |
| 37 | sc-112 Embed fetched data on write | 3 | Low | Hooks into the raw-fetch write path. |
| 38 | sc-113 Backfill embeddings | 2 | Low | After sc-112. |
| 39 | sc-114 Parallel semantic search tool | 3 | Low | After sc-111..113. |
| 40 | sc-115 Search-first prompting + eval | 2 | Low | After sc-114; overlaps sc-163. |
| 41 | sc-116 Spin up sub-agent tool | 5 | Low | Independent; sc-204's summary will describe it. |
| 42 | sc-117 Sub-agent guardrails | 2 | Low | Ships with sc-116. |
| 43 | sc-118 Sub-agent progress in the UI | 2 | Low | Chat UI, so after sc-138. |
| 44 | sc-123 Spike: define log upload scope | 2 | Low | Gates the rest of epic 102. |
| 45 | sc-124 Log upload endpoint and storage | 2 | Low | After the spike. |
| 46 | sc-125 Log upload UI with progress | 2 | Low | After sc-124. |
| 47 | sc-126 Ingest uploaded logs for the agent | 5 | Low | Into the stored-fetch shape (sc-130), so after it. |
| 47a | sc-216 One shared naive-timestamp-as-UTC helper | 1 | Low | Five copies on base (constitution I); 029 adds the helper, this moves the rest. |
| 48 | sc-171 wcl_agent follow-ups: de-stutter module names | 2 | Low | Cheap, but no feature waits on it. |
| 49 | sc-173 Add ruff with isort rules | 2 | Low | Mechanical; touches many files, so best between sprints. |
| 50 | sc-172 ai_guide.md stale facts | 1 | Low | Docs only. |
| 51 | sc-174 Perf test test_wcl_loop_lag fails under -m perf | 1 | Low | Opt-in suite; fails at base too. |
| 52 | sc-119 (Long term) Sandboxed execution service | 5 | Lowest | Only needed for the REPL. |
| 53 | sc-120 (Long term) REPL tool for sub-agents | 5 | Lowest | Needs sc-116 and sc-119. |
| 54 | sc-121 (Long term) Load log data into the REPL | 2 | Lowest | Needs sc-120 and stored data. |
| 55 | sc-122 (Long term) Sandbox security review | 2 | Lowest | Gates shipping sc-119/120. |
| 55a | sc-241 QA invalid proposal item crashes the turn (`qa-deferred`, **crucial**) | 2 | High | Owner's call: crucial QA findings get High. Fix first next sprint; it can break the example request live. |
| 55b | sc-242 QA overlapping approvals: double follow-up or 500 (`qa-deferred`, crucial) | 2 | Medium | Crucial; small, same files as sc-241. |
| 55c | sc-243 QA card in the wrong chat after a mid-turn switch (`qa-deferred`, crucial) | 2 | Medium | Crucial; small frontend guard plus a label. |
| 56 | sc-177 QA raw_fetches write amplification and growth (`qa-deferred`) | 3 | Lowest | QA tier, top: same table as sc-178/sc-129, do it alongside them. |
| 57 | sc-158 QA SEC-004 per-client login limit (`qa-deferred`) | 2 | Lowest | QA tier; needed before any shared deployment (sc-146). |
| 58 | sc-157 QA SEC-003 block remote images (`qa-deferred`) | 2 | Lowest | QA tier; small, frontend only. |
| 59 | sc-185 QA Postgres tenant-isolation tests in CI (`qa-deferred`) | 3 | Lowest | QA tier; more valuable now that the agent writes tenant data (epic 203). |
| 60 | sc-176 QA switch to the sibling model sooner on 429s (`qa-deferred`) | 2 | Lowest | QA tier; makes the 021 fallback save time. |
| 61 | sc-156 QA PERF-001 don't block on discovery (`qa-deferred`) | 2 | Lowest | QA tier; pair with sc-159 (same files). |
| 62 | sc-159 QA SPEC-002/004 log line + empty catalog (`qa-deferred`) | 1 | Lowest | QA tier; pair with sc-156. |
| 63 | sc-179 QA generated-title cleaning (`qa-deferred`) | 2 | Lowest | QA tier. |
| 64 | sc-180 QA conversation-list state (`qa-deferred`) | 2 | Lowest | QA tier. |
| 65 | sc-183 QA welcome M+ edge cases (`qa-deferred`) | 2 | Lowest | QA tier; confirm with live data first. |
| 66 | sc-184 QA web search after fallback (`qa-deferred`) | 2 | Lowest | QA tier; needs a live check first. |
| 67 | sc-182 QA M+ refresh efficiency (`qa-deferred`) | 2 | Lowest | QA tier. |
| 68 | sc-181 QA sidebar activity order (`qa-deferred`) | 1 | Lowest | QA tier; predates the last sprint. |
| 69 | sc-221 QA SEC-001/002/003 harden the agent write path against injected log text (`qa-deferred`) | 3 | Lowest | **Top deferred security item** (the only Medium security finding on the new write path). Do it right after sc-241..243. |
| 70 | sc-222 QA SEC-004/005 identity context reset + user-level RLS (`qa-deferred`) | 2 | Lowest | QA tier; defence in depth, do with sc-185. |
| 71 | sc-220 QA preamble budgets and cost with many friends (`qa-deferred`) | 3 | Lowest | QA tier; matters once users bulk-add friends. |
| 72 | sc-219 QA confirmation card state edge cases (`qa-deferred`) | 3 | Lowest | QA tier; cosmetic or rare multi-tab cases. |
| 73 | sc-225 QA proposal approve/read DB round trips, guide fan-out (`qa-deferred`) | 2 | Lowest | QA tier. |
| 74 | sc-223 QA profile cap race + legacy slug duplicates (`qa-deferred`) | 2 | Lowest | QA tier. |
| 75 | sc-224 QA cache participants lookups (`qa-deferred`) | 1 | Lowest | QA tier; the 028 design's planned follow-up. |
| 76 | sc-244 QA architecture docs and contracts stale for the self-aware agent (`qa-deferred`) | 1 | Low | Crucial-list docs item; the owner set Low. |
