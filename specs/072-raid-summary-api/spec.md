# Feature Specification: Raid summary from stored data

**Feature Branch**: `072-raid-summary-api`

**Created**: 2026-11-07

**Status**: Draft

**Input**: Backend half of Shortcut sc-142 "Raids page: show previously pulled raid data": "As a
user, I want each raid to show stored data (participants, duration, my character's parse), so I
can review it without a chat." Contract `contract:raid-summary` on the team board (producer 072,
consumer 073).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what was stored about a tracked raid (Priority: P1)

A user opens a raid tab on the Raids page. The page asks the server for that raid's summary and
shows who took part (name, class, spec, role), how long the raid lasted, and when the data was
fetched, without starting a chat and without any new Warcraft Logs request.

**Why this priority**: it is the story's value: reviewing a raid without a chat.

**Independent Test**: seed a tracked raid and its stored report summary for a workspace, call the
summary endpoint as that workspace, and compare the answer with the contract example.

**Acceptance Scenarios**:

1. **Given** a raid tracked in my workspace whose report summary is stored and visible to my
   workspace, **When** I ask for its summary, **Then** I get the participants, the duration and
   the time it was fetched, in the contract's shape.
2. **Given** a raid tracked in my workspace with nothing usable stored, **When** I ask for its
   summary, **Then** I get `has_data: false`, null duration and fetch time, and empty lists.
3. **Given** a raid whose stored data is visible, **Then** no Warcraft Logs request is made.
4. **Given** a raid whose stored summary is outside the visibility window, **When** I ask for its
   summary, **Then** one report-summary request re-verifies it and the stored data is served.

---

### User Story 2 - See my own characters' parses in that raid (Priority: P2)

For each of my own profile characters that took part, the summary lists the parse percentile per
boss kill (encounter, difficulty, percentile), when the rankings were stored.

**Why this priority**: "my character's parse" is named in the story, but it depends on rankings
having been fetched before; participants and duration come first.

**Independent Test**: seed stored rankings naming my profile character (same name and realm) and
another character with the same name on another realm; only mine is listed.

**Acceptance Scenarios**:

1. **Given** stored rankings for the raid and an own profile character in them, **When** I ask
   for the summary, **Then** `my_characters` lists that character with its parses.
2. **Given** a player in the raid with my character's name but another realm, **Then** that player
   is not listed as mine.

---

### User Story 3 - Nothing leaks across workspaces (Priority: P1)

A raid that is not tracked by my workspace, or stored data my workspace may not see, never shows
up in my summary.

**Why this priority**: tenant isolation over the shared stored WCL data is security-core.

**Independent Test**: hostile-input tests listed under Edge Cases, each asserted on the response.

**Acceptance Scenarios**:

1. **Given** a report code tracked only by another workspace, **When** I ask for its summary,
   **Then** I get 404 and nothing of that raid.
2. **Given** a stored, public report that my workspace does not track, **Then** I get 404.
3. **Given** a tracked raid whose stored rows are visible only to another workspace (granted to
   it, not public), **Then** those rows are not used: `has_data: false`.

### Edge Cases

- A report code with path tricks (`..%2F`, `\`, a newline, 300 characters, Unicode look-alike
  letters) is rejected (404 or 422) before any database query, never a crash.
- Uploader-controlled text (player names, specs) is returned as plain data: angle brackets and
  look-alikes neutralised, control characters removed, capped in length. A 5 000-character name
  comes back capped.
- A stored body that is malformed in any part (wrong types, missing keys) yields null/empty for
  that part, never an error.
- A huge stored roster is capped at a fixed number of participants.
- Rankings stored only for some bosses yield parses for those bosses only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST answer a summary request only for a report tracked in the caller's
  workspace; any other code gets 404 with the app's usual error body.
- **FR-002**: The system MUST NOT fetch participants, tables or rankings from Warcraft Logs. Only
  when a summary of the raid is stored but its visibility isn't confirmed inside the window, it
  MAY send ONE report-summary request to re-verify it (PO `decision:072-reverify`), bounded by a
  short timeout and a per-workspace, per-raid cooldown; failure means `has_data: false`.
- **FR-003**: The system MUST read stored WCL data only through the existing stored-data
  visibility rule (every report a row names is public or granted to the caller's workspace,
  confirmed within the re-verify window).
- **FR-004**: The answer MUST contain `report_code`, `has_data`, `duration_ms`, `participants`
  (name, class_name, spec, role), `my_characters` (name, class_name, spec, parses of encounter,
  difficulty, percentile) and `fetched_at`, as in the contract.
- **FR-005**: Each part MUST be null/empty on its own when its stored source is missing;
  `has_data` is true when any part is present.
- **FR-006**: `role` MUST be one of tank, healer, dps or null; `percentile` MUST be 0–100 or null.
- **FR-007**: "My characters" MUST come from the caller's own profile characters (server-side
  rows), matched to stored players by name and, where the stored data has them, realm and region;
  never from request input.
- **FR-008**: Uploader-controlled strings MUST be neutralised, stripped of control characters and
  capped; the participant list MUST be capped.
- **FR-009**: Report codes MUST be validated (ASCII letters and digits, at most 32 characters)
  before any query.

### Key Entities

- **Raid summary**: the response; one per tracked raid and request.
- **Participant**: a player seen in the stored report data.
- **My character**: an own profile character found among the participants or the rankings.
- **Parse**: a percentile for one boss kill of one of my characters.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a seeded raid, the summary equals the contract's shape (keys and types).
- **SC-002**: Every hostile input in Edge Cases and User Story 3 has a test that passes.
- **SC-003**: Zero Warcraft Logs requests for a raid whose stored data is visible or absent; at
  most one report-summary request per raid and cooldown otherwise.
- **SC-004**: A summary needs a fixed small number of database round trips, independent of the
  number of fights or players.

## Assumptions

- Stored data comes from the agent's own WCL queries (report summary, participants/player
  details, per-boss Summary tables, report rankings); only those exact shapes are read.
- Data appears only for raids whose visibility was confirmed within the store's re-verify window;
  older raids show `has_data: false` until a chat or the recent-raids refresh fetches them again.
- Parses use the rankings tool's default comparison (Rankings, Historical), so all listed
  percentiles mean the same thing.

## Clarifications

### Session 2026-11-07 (answered by the developer, board decisions)

- Q: Which visibility window applies? → A: the store's own (`since` = now − re-verify days); older
  raids show `has_data: false` (`scope:072:visibility-window`).
- Q: Which stored rows are read? → A: the newest visible own report summary naming the code, plus
  the exact rows our own tools would have stored for it (participants/player details for the whole
  report, per-boss Summary tables, default rankings for the whole report and per boss)
  (`scope:072:sources`).
- Q: Which rankings comparison, and is a freshness rule applied? → A: Rankings/Historical only; no
  freshness rule, `fetched_at` is the newest row used; caps 100 participants, 60 chars, 50 parses
  (`scope:072:parses`).
- Q: How is a bad report code answered? → A: 404 `not_found` (same as an unknown raid, reveals
  nothing), decided in a dependency before the tenant transaction opens.
