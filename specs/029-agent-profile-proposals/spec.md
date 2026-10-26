# Feature Specification: Capability Summary and Profile Proposal Tools

**Feature Branch**: `029-agent-profile-proposals`

**Created**: 2026-10-26

**Status**: Draft

**Input**: User description: "Feature 029 (sc-204 + sc-205, epic 203 "Self-aware agent"): capability summary + profile proposal tools. (1) sc-204: Barnaby's system prompt carries a short capability summary generated from the tools actually registered (no hand-maintained tool list), stating what he can change (own characters and friends incl. raid roles, always through a proposal the user approves) and what he cannot, within a token budget. (2) sc-205: Barnaby can read the current user's profile and propose adding, updating (raid role) and removing own characters and friends in bulk; the tool never writes — it returns a stored change proposal (tenant/user/conversation bound, 30-minute expiry, per-item validation: realm/region, duplicates by realm slug, limits incl. a new 50-friend cap, hostile-name guard). Executing an approved proposal goes through one shared profile service also used by the REST profile endpoints; execution is idempotent with per-item results. Agreed design: documentation/designs/self-aware-agent/capabilities-and-tools.html (C1-C14, #proposal-contract), sprint decisions D4-D11."

**Agreed design (cited, not re-derived)**: `documentation/designs/self-aware-agent/capabilities-and-tools.html`
(decisions C1–C14, `#proposal-contract`, `#validation-codes`, `#proposal-service-api`, Tests, Files)
and the sprint decisions `sprints/2026-10-26/decisions.md` D4–D11. Where this spec says "per the
design", the design's decision is binding.

## Clarifications

### Session 2026-10-26

- Q: Should the capability summary also name app features that have no tool (sc-204's story text lists profile, raids, class guides, PDF reports, chat filters)? → A: Yes, option B (PO decision D13): one fixed app-facts line, naming only features that exist on the base, with no tool names, inside the budget. There is no per-chat character filter (sc-144 isn't built), so it is not named; the boss checkboxes under a report (EncounterPicker) are. There is no separate Raids page on the base; recent raids and Mythic+ runs are on the welcome screen.

## Scope

**In scope (this feature)**: the generated capability summary (sc-204); the profile change
proposal tool, proposal storage, validation, and the proposal service that 031's transport will
call (create, list, get, execute, cancel) (sc-205); the shared profile write path used by both the
REST profile endpoints and proposal execution; the 50-friend cap (D8) including a readable message
on the profile page; realm-slug duplicate detection in the shared identity check.

**Out of scope (other features)**: the confirmation card, stream frames, the REST approve/cancel
routes and the `message_seq` assignment (031); participant resolution from a run (030); per-item
selection on the card (sc-214); tightening manual entry rules; WCL existence lookups for names.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Barnaby knows what the app lets him do (Priority: P1) — sc-204

A user asks Barnaby "can you add my friends?" or "what can you do?". Barnaby answers from an
accurate, short summary of the tools he actually has in this session, including which profile
changes he can propose (own characters and friends, including raid roles, always subject to the
user's approval) and what he cannot do (the guild, settings, other users' data, writing anything
without approval). When a tool is added to or removed from the agent, the summary follows
automatically; nobody edits prose.

**Why this priority**: Without it Barnaby says he can't do things he can, or claims abilities he
lacks. Every later agent tool is described for free.

**Independent Test**: Build the agent with and without an extra tool and compare the summary in
its system instruction; no prose edit is needed for the change to appear or disappear.

**Acceptance Scenarios**:

1. **Given** the backend agent with the profile tool registered, **When** its system instruction
   is built, **Then** it contains one line per registered tool (including the profile tool) and
   the "can change / cannot" boundary lines.
2. **Given** a fake tool added to a tool group, **When** the summary is rendered, **Then** the
   tool appears; **When** it is removed, **Then** it disappears, with no change to the
   instruction text.
3. **Given** a model without web search (Claude), **When** the summary is rendered, **Then** it
   says web search is not available in this session.
4. **Given** the largest tool set (Gemini, web search, profile tool), **When** the summary is
   rendered, **Then** it stays within the design's budget (≤ 4,000 characters, each tool line
   ≤ 160 characters).
5. **Given** the CLI agent (no backend), **When** its summary is rendered, **Then** it does not
   claim profile changes.

---

### User Story 2 - Barnaby proposes profile changes, the user decides (Priority: P1) — sc-205

A user says "add Thrall and Jaina from Tarren Mill EU to my friends, make my Alt a healer and
remove Bob". Barnaby reads the current profile (already in his per-turn context), calls the
proposal tool once with all changes, and gets back a stored proposal listing every item with a
validation result. Nothing on the profile changes. He tells the user what is proposed, which
items will be skipped and why, and that nothing has changed yet.

**Why this priority**: This is the core of epic 203 and the first agent write path to tenant
data; it must be safe by construction.

**Independent Test**: Call the tool in a turn context with a mixed list (valid adds, a
duplicate, a hostile name, an update, a remove of an unknown character) and check the returned
proposal, the stored row, and that the profile is unchanged.

**Acceptance Scenarios**:

1. **Given** an authenticated chat turn, **When** Barnaby proposes adds, role updates and
   removals for own characters and friends (1–30 items), **Then** a pending proposal is stored
   for that tenant, user and conversation, and returned in the contract shape with a validation
   result per item, plus a note that nothing has changed yet.
2. **Given** any proposal call, **Then** the user's characters and friends are unchanged
   afterwards.
3. **Given** more than 30 items, **When** the tool is called, **Then** it returns a tool error
   (no proposal) so Barnaby can ask the user to narrow the set.
4. **Given** a character name from a log that contains instruction-like text, spaces, digits or
   punctuation, **When** it is proposed, **Then** the item is marked invalid (`invalid_name`),
   shown as skipped, and can never be applied.
5. **Given** an item that adds a friend who is already a friend, or the same realm written
   differently ("Tarren Mill" vs "tarren-mill"), **Then** the item is marked `duplicate_friend`.
6. **Given** an update or remove that names a character not on the profile, **Then** the item is
   marked `not_found`; an update to the role it already has is marked `no_change`.
7. **Given** a turn with no authenticated user (the greeting) or a mismatched tenant, **When**
   the tool is called, **Then** it fails closed with an error and stores nothing.
8. **Given** an add without an explicit role request, **Then** the item's raid role is empty
   (inferred later from the spec, D9); a role is set only when the user asked for one.

---

### User Story 3 - An approved proposal is applied exactly once, safely (Priority: P1) — sc-205

When the user approves (031's card calls the service), every item that is still valid is applied
through the same profile write path the profile page uses; invalid items are skipped; items that
became invalid in the meantime fail individually. The proposal then shows each item's result.
Approving twice changes nothing more. Another tenant's or user's proposal can't be executed, and
an expired one can't either.

**Why this priority**: Correctness and tenant safety of the write are the security core of
sc-205 and gate 031.

**Independent Test**: Through the service only (no UI): execute, re-execute, execute as another
tenant/user, execute after expiry, cancel; check the profile rows and the returned results.

**Acceptance Scenarios**:

1. **Given** a pending proposal with valid, invalid and (by execution time) conflicting items,
   **When** it is executed, **Then** the valid items are applied, invalid ones are `skipped`,
   conflicting ones are `failed` with their code, and the proposal becomes `applied`.
2. **Given** an applied proposal, **When** it is executed again, **Then** the same result comes
   back and no profile row changes.
3. **Given** a proposal of tenant A, **When** a user of tenant B, or another user of tenant A,
   executes, gets or cancels it, **Then** it fails as not found (no disclosure).
4. **Given** a pending proposal older than 30 minutes, **When** it is executed, **Then** it fails
   as expired, nothing is written, and its stored status becomes `expired`.
5. **Given** a pending proposal, **When** it is cancelled, **Then** nothing is written and it is
   `cancelled`; cancelling again is a no-op; executing a cancelled proposal fails as cancelled;
   cancelling an applied one fails as applied.
6. **Given** characters added by an executed proposal, **Then** each gets its background guide
   task, scheduled once and only after the change is committed.
7. **Given** a conversation with several proposals, **When** they are listed for that user,
   **Then** all come back oldest first with their real status (pending, applied, cancelled,
   expired).

---

### User Story 4 - One write path and a friend cap for everyone (Priority: P2) — sc-205, D8

Adding, re-roling and removing characters behaves the same whether the user types it on the
profile page or approves Barnaby's proposal. A profile can hold at most 50 friends: the 51st add
is refused with `friend_limit` on both paths, and the profile page shows a readable message.
Profiles already over 50 keep all their friends. Duplicate detection treats realm spellings that
differ only by case, spaces vs hyphens or apostrophes as the same realm, on both paths.

**Why this priority**: Required by sc-205 ("no second write path") and D8, but invisible to the
user except for the cap message.

**Independent Test**: The existing profile API tests pass unchanged; a 51st friend add over REST
returns 409 `friend_limit`; "Tarren Mill" then "tarren-mill" is a duplicate over REST.

**Acceptance Scenarios**:

1. **Given** the existing profile API test suite, **When** it runs after this feature, **Then**
   it passes unchanged.
2. **Given** 50 friends, **When** the user adds one more on the profile page, **Then** it is
   refused and the page shows a readable "friend limit reached" message.
3. **Given** a profile with more than 50 friends, **Then** all are kept and listed; only new adds
   are refused.
4. **Given** a friend on "Tarren Mill", **When** the same name is added on "tarren-mill" in the
   same region, **Then** it is refused as a duplicate.

---

### Edge Cases

- Same identity twice in one proposal: the second is `duplicate_item`.
- Own-character adds counted ahead: an 11th own character within one proposal is
  `character_limit`; the 51st friend is `friend_limit`, counting earlier adds in the proposal.
- Adding as a friend a character that is one of the user's own: `already_own`; adding as own a
  saved friend: `already_friend`.
- A friend added by hand between proposal and approval: that item fails as `duplicate_friend`;
  the others still apply.
- A character removed by hand between proposal and approval: that item fails as `not_found`.
- Region outside us/eu/kr/tw/cn: `invalid_region`; realm with disallowed characters:
  `invalid_realm`; any other schema failure (e.g. too long): `invalid_item`.
- Real names and realms must pass: accented names, "Area 52", "Kel'Thuzad", "Azjol-Nerub".
- Two concurrent approvals of the same proposal (double click, two tabs): applied once.
- Older pending proposals in the same chat stay valid until they expire (D11-3).
- A crash during execution: nothing is half-applied; the proposal stays pending.

## Requirements *(mandatory)*

### Functional Requirements

**Capability summary (sc-204)**

- **FR-001**: The agent's system instruction MUST carry a capability summary generated from the
  exact tool list registered on that agent, using each tool's own name and description; the
  hand-written tool list MUST be removed and no registered tool name may appear literally in the
  fixed instruction text (C1, C4).
- **FR-002**: The summary MUST include the fixed usage rule (only tools exposed in this session,
  parallel independent calls), a line per tool, a "you can change" line emitted only when the
  profile tool is registered (own characters and friends including raid roles, only through a
  proposal the user approves), and a "you cannot" line (guild, settings, other users' data,
  writing without approval) (C1), and one fixed app-facts line naming the app features the user
  uses themselves that exist on the base: the Profile page (own characters, friends, main guild,
  raid roles, Class guides tab), recent raids and Mythic+ runs on the welcome screen, PDF download
  of a reply, the boss checkboxes under a report, and the model picker. The line names no tool and
  no feature that isn't built (D13).
- **FR-003**: When web search is not registered, the summary MUST say so and tell Barnaby to state
  that current-patch verification was not possible (C4).
- **FR-004**: The summary MUST stay within 4,000 characters for the largest tool set, with each
  tool line ≤ 160 characters (C3); it MUST sit in the cacheable system instruction, not the
  per-turn preamble (C2).
- **FR-005**: Usage hints in today's hand-written list that don't fit one line MUST live in the
  tools' descriptions or the existing policy sections, per the design's hint table (C4).
- **FR-006**: The CLI agent without the backend MUST keep working, with no profile claims in its
  summary (C4, C6).

**Profile proposals (sc-205)**

- **FR-007**: The agent MUST have exactly one profile tool that accepts 1–30 change items
  (action add/update/remove, target own/friend, name, realm, region, optional class, spec, raid
  role, played role) and returns a stored proposal in the design's contract shape. It MUST NOT
  accept tenant, user, conversation or record-id arguments (C5, C7).
- **FR-008**: The tool MUST NOT change the profile; it validates, stores and returns the proposal
  with the note that nothing has changed yet. More than 30 items MUST be a tool error (C5, C13).
- **FR-009**: The acting tenant, user and conversation MUST come from the authenticated chat turn
  only; with no identity or a tenant mismatch, the tool MUST fail closed and store nothing (C7).
- **FR-010**: Each item MUST be validated with the same schema as manual entry, then the identity
  rules for proposals (name, realm, region), duplicates by realm slug against the live profile
  and within the proposal, limits counted ahead (10 own, 50 friends), and existence for
  update/remove; each item gets `ok` plus one of the design's validation codes and a short
  message (C12, C13, `#validation-codes`).
- **FR-011**: Update and remove items MUST be addressed by name, realm, region and target, and
  resolved to the existing record on the server; "update" changes the raid role only (C5).
- **FR-012**: An add item's raid role MUST stay empty unless the user asked for a role; the
  played role is display-only and never stored (D9).
- **FR-013**: A proposal MUST be stored durably, bound to its tenant, user and conversation, with
  status pending/applied/cancelled/expired, created/expiry/applied times, a nullable link to the
  agent message (set later by 031), and an expiry 30 minutes after creation; "expired" is
  computed on read and execute (C9, C10).
- **FR-014**: The service MUST offer create, list (per conversation, oldest first), get, execute
  and cancel, each scoped to the acting tenant and user and opening its own tenant-scoped
  transaction; a proposal of another tenant or user MUST be reported as not found
  (`#proposal-service-api`).
- **FR-015**: Execution MUST be idempotent and atomic: claim the proposal under a row lock,
  re-validate every originally valid item against the current profile, apply each still-valid
  item in its own savepoint through the shared write path, record each item's result
  (applied/skipped/failed with code and new record id), mark applied, commit once, and only then
  schedule guide tasks for added characters. A second execution returns the stored result and
  writes nothing (C11).
- **FR-016**: Expired proposals MUST NOT be executable (error `proposal_expired`, status stored);
  cancelled ones fail with `proposal_cancelled`; cancelling an applied one fails with
  `proposal_applied`; cancelling twice is a no-op (`#proposal-service-api`).
- **FR-017**: The proposal store MUST have the same tenant row-level security as the other tenant
  tables, and its schema change MUST upgrade and downgrade cleanly (C9).

**Shared write path, friend cap, duplicates (sc-205, D8)**

- **FR-018**: Adding, re-roling and removing profile characters MUST go through one shared
  profile service used by both the REST profile endpoints and proposal execution; the REST
  endpoints keep their signatures, status codes and error details (C8).
- **FR-019**: A profile MUST NOT gain a 51st friend through any path; the refusal code is
  `friend_limit` (REST 409 detail and proposal validation). Profiles already over 50 keep every
  friend (D8).
- **FR-020**: The profile page MUST show a readable message for `friend_limit` (D8).
- **FR-021**: Duplicate detection in the shared identity check MUST compare realms by slug (case,
  surrounding whitespace, spaces vs hyphens, apostrophes), so REST adds and proposal execution
  see the same identity; the stored realm keeps its original spelling (C12).

**Prompt-injection guard (sc-205)**

- **FR-022**: Names and realms from any source (including WCL data) MUST pass the same validation
  as manual entry plus the proposal identity rules before they can be applied; a hostile name is
  marked invalid and never written (C14).

### Key Entities

- **Capability summary**: generated text derived from the registered tool groups; one line per
  tool plus fixed rule and boundary lines.
- **Tool group**: a labelled, ordered set of agent tools with an optional rule note (e.g.
  "proposals only").
- **Profile change proposal**: id, conversation, optional agent-message link, status, created /
  expires / applied times, 1–30 items; bound server-side to tenant and user.
- **Proposal item**: index, action, target, name, realm, region, class, spec, raid role, played
  role, previous raid role, resolved character id, validation result, execution result.
- **Profile character** (existing): an own character or friend of a tenant; now capped at 50
  friends.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding or removing a tool changes Barnaby's capability summary with zero edits to
  instruction prose (shown by a test).
- **SC-002**: The capability summary for the largest tool set is ≤ 4,000 characters (about 1,000
  tokens) and every tool line ≤ 160 characters (asserted by a test).
- **SC-003**: 100% of proposal calls leave the profile unchanged until approval (tool and
  scripted agent-turn tests).
- **SC-004**: A hostile character name is never applied to a profile (test).
- **SC-005**: Cross-tenant, cross-user, expired and repeated executions each change zero profile
  rows (one test per case).
- **SC-006**: The existing profile API tests pass unchanged, and the full backend suite has no
  new failures against the base (baseline counts recorded in the checkpoint).
- **SC-007**: On a real database, the proposal store upgrades and downgrades cleanly and denies
  cross-tenant reads and writes (Postgres-only tests).
- **SC-008**: An offline scripted agent turn (fake model, real runner and tool) with a hostile
  name and a mix of valid items produces the expected proposal and leaves the profile unchanged.

## Assumptions

- Part 1's open questions take the recommended options (D11-3): identity rules for proposals
  only (REST entry unchanged); syntax and duplicate checks only, no WCL existence lookup; older
  pending proposals stay valid until they expire.
- Reads of the profile use the existing per-turn KNOWN PLAYER CONTEXT preamble; no separate read
  tool (C5). After approval, Barnaby sees the applied profile from his next turn (D10).
- The approve/cancel outcome does not enter the agent session (D10); 031 owns frames, routes and
  the message link assignment. 029 changes one line of the chat socket handler only, to make the
  acting identity available to the tool.
- The 30-minute expiry and the name/realm patterns are design inferences; each is one constant.
- A tenant's members share one profile; approval is still bound to the proposing user (stricter,
  per the design).
- Two concurrent own-character adds may exceed the 10 limit by one (pre-existing REST race,
  accepted in the design).
- Live agent-eval cases are optional; the offline scripted agent test is required (D11-4).
