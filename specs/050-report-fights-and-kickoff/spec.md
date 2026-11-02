# Feature Specification: Report fights and kickoff

**Feature Branch**: `050-report-fights-and-kickoff`

**Created**: 2026-11-02

**Status**: Draft

**Input**: Sprint 2026-11-02 brief 050 (stream A): sc-365, sc-330, sc-358, sc-351.

## Clarifications

### Session 2026-11-02

Answered by the developer under the autonomous steer; each is a board `answer` entry.

- Q: Order kills by end time (new upstream field) or by start time? → A: Start time, falling
  back to fight id; fights do not overlap, so this matches end time with no query or cache
  change (`clarify:050-last-kill-order`).
- Q: Do Mythic+ key runs count as boss kills? → A: No; they are excluded from `last_kill` and
  the per-boss summary, and carry their keystone level in the fight list.
- Q: Kickoff playbook: move into the visible kickoff prompt, or keep it in the instruction for
  kickoff turns only? → A: Instruction, kickoff turns only, recognised by the server-owned
  kickoff opening; the visible first message stays short (`clarify:050-playbook`).
- Q: How does the kickoff ask for the slim view? → A: An `overview` flag on the table tool
  (default off), same upstream query (`clarify:050-overview`).
- Q: Neutralise into which characters? → A: Every angle-bracket look-alike, after entity
  decoding and NFKC to a fixed point, becomes `(` or `)`; labels and sections get their own
  data blocks, capped at 120 (`clarify:050-untrusted`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - "The last boss kill" means the last kill in the report (Priority: P1, sc-365)

A raider asks about "the last boss kill" of a report, twice in different words (a top-3 list,
then a bar chart). Both answers must be about the same boss: the last boss killed in that
report. Today the model guesses from a flat fight list without times; on a report that starts
with Mythic+ keys, a timed key looked like a boss kill, and on a long night the list is cut to
its early fights.

**Why this priority**: a wrong fight makes every number in the answer wrong, and the user
cannot tell.

**Independent Test**: the fights tool on a fixture with trash, M+ keys, wipes and several kills
(kill order differing from fight id order, and a list larger than the result cap) names the
right last kill, and the instruction tells the model to use it.

**Acceptance Scenarios**:

1. **Given** a report with several boss kills, **When** the fights tool runs, **Then** its
   result names the last kill (fight id, boss name, difficulty), chosen by time, never by
   list position.
2. **Given** a report with no boss kill, **When** the fights tool runs, **Then** the last kill
   is empty (null) and the per-boss summary still lists the pulls.
3. **Given** a report whose full fight list exceeds the result cap, **When** the fights tool
   runs, **Then** the last kill and the per-boss summary are still complete.
4. **Given** a report that starts with timed Mythic+ keys, **When** the fights tool runs,
   **Then** no key run is reported as the last boss kill.
5. **Given** the agent instruction, **When** a user asks about "the last kill / last boss",
   **Then** the instruction tells the model to use the last-kill field.

---

### User Story 2 - Cheaper recent-raid kickoff (Priority: P2, sc-358)

A user clicks a recent raid. The kickoff overview answer is gathered from one per-boss table
per boss. Today each table repeats the roster several times and carries per-player details,
and every chat request carries the kickoff playbook even when no kickoff happens.

**Why this priority**: token cost and latency of the most common first turn.

**Independent Test**: on the synthetic 20-player fixture, the kickoff answer request (the
instruction plus the fight list plus one table per boss) is at least 15k tokens (chars/4)
smaller than today; other requests carry no kickoff playbook.

**Acceptance Scenarios**:

1. **Given** the kickoff turn, **When** the model asks for each boss's Summary table in the
   slim view, **Then** each list has at most 10 rows with plain fields, and there is no
   per-player details block and no composition list.
2. **Given** any non-kickoff turn, **When** the instruction is built, **Then** it does not
   contain the kickoff playbook; **Given** the kickoff turn, **Then** it does.
3. **Given** a non-kickoff Summary request, **When** the table tool runs, **Then** the
   result has today's shape.
4. **Given** the kickoff pre-fetch warmed the tables, **When** the turn asks for the slim view,
   **Then** it is served from the same stored data (same upstream query).

---

### User Story 3 - No uploader text outside the data marking (Priority: P2, sc-351)

Report titles, guild names, player names and guide section headings are written by other
people. Knowledge-search results must present them only as marked data the model never
follows, and no encoding trick may close the data block early.

**Why this priority**: prompt injection through shared data is a security risk.

**Independent Test**: search payloads built from hostile labels, sections and texts keep every
such string inside a data block that no look-alike delimiter can close; report tools cut
over-long uploader strings.

**Acceptance Scenarios**:

1. **Given** a search hit, **When** the payload is built, **Then** its label and section are
   inside data blocks, neutralised and capped like the hit text.
2. **Given** text containing `</data>`, `＜/data＞`, `&lt;/data&gt;`, double-encoded entities,
   or the replacement characters themselves, **When** it is neutralised, **Then** no closing
   delimiter or look-alike of one remains.
3. **Given** a report whose title, guild, player or fight names are very long, **When** the
   report tools return them, **Then** each is cut to its stated length.
4. **Given** the 044 search contract, **When** it is read, **Then** it shows the result shape
   the code returns.

---

### User Story 4 - One difficulty map (Priority: P3, sc-330)

The difficulty id-to-name map exists twice. There must be one, used by every caller, with no
change in any output.

**Independent Test**: both former definitions are gone, every user imports the shared map,
and existing tests pass unchanged.

**Acceptance Scenarios**:

1. **Given** the codebase, **When** searched, **Then** exactly one difficulty id-to-name map
   exists, in the game reference package.

### Edge Cases

- Several kills of the same boss (farm night): the last kill is the latest by time.
- Kills of the same boss on two difficulties: the per-boss summary lists each difficulty once.
- Fights without a start time (old cached summaries): ordering falls back to fight id.
- Mythic+ key runs in a raid report: excluded from the last kill and the per-boss summary.
- Neutralising must be idempotent and leave ordinary text readable.
- A name exactly at its cap is kept whole; one character longer is cut with an ellipsis.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The fights tool MUST return `last_kill` (fight id, boss name, encounter id,
  difficulty id and name) for the latest boss kill by time, or null when no boss was killed.
- **FR-002**: The fights tool MUST return a per-boss summary (boss, difficulty, pulls, kills,
  last kill fight, last pull fight) in first-pull order.
- **FR-003**: Both MUST be computed from the full fight list and placed outside the capped
  fight list.
- **FR-004**: Key runs (fights with a keystone level) MUST NOT count as boss kills or bosses.
- **FR-005**: The agent instruction MUST tell the model to use `last_kill` for last-kill and
  last-boss questions.
- **FR-006**: The table tool MUST offer a slim overview view: at most 10 rows per list, plain
  fields only, no per-player details, no composition list; the default view is unchanged.
- **FR-007**: The kickoff playbook MUST be in the instruction only for kickoff turns, and it
  MUST tell the model to use the slim view.
- **FR-008**: A prompt-size regression test MUST show the kickoff answer request at least 15k
  tokens (chars/4) smaller than today's on the synthetic 20-player fixture.
- **FR-009**: Search hit labels and guide sections MUST be wrapped as data and capped.
- **FR-010**: Neutralising MUST decode HTML entities, apply NFKC and remove format characters
  (Unicode Cf) to a fixed point, then replace every angle-bracket look-alike, including the old
  replacement characters; length caps apply after it (P7 SEC-002/003/004).
- **FR-011**: The report tools MUST neutralise uploader strings and cap report titles at 80
  characters and guild, player and fight names (and every string in a returned table) at 60;
  the total per result is bounded (players map and fight list 60,000 characters, at most 40
  bosses, tables 40,000) (P7 SEC-001/005).
- **FR-012**: The 044 search contract MUST match the payload shape.
- **FR-013**: One difficulty id-to-name map in the game reference package; no output change.

### Key Entities

- **Last kill**: the latest boss kill of a report (fight id, boss, difficulty).
- **Boss summary**: one row per boss and difficulty with pull and kill counts and the fights
  to inspect.
- **Slim overview view**: the per-boss table projection used by the kickoff.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a multi-kill fixture, the fights tool names the right last kill in 100% of
  orderings tested, including a list larger than the cap.
- **SC-002**: The kickoff answer request on the synthetic 20-player fixture shrinks by at
  least 15k tokens; non-kickoff requests lose the playbook (~190 tokens each).
- **SC-003**: No tested delimiter variant closes a data block early.
- **SC-004**: Live (team-lead): two differently worded "last boss kill" questions on report
  BKNtypgnhrxXvj84 both name Ula'tek (fight 32); a recent-raid kickoff answers with a prompt
  under about 35k tokens.

## Assumptions

- Fights in one report do not overlap, so the latest start is the latest end; no end-time
  fetch is needed (board `clarify:050-last-kill-order`).
- The kickoff turn is recognised by the server-owned kickoff wording at the start of the
  turn's user message; this selects a playbook only and is no security gate
  (board `clarify:050-playbook`).
- 8 boss tables (one raid tier) is the measured kickoff shape.
- Other report tools that carry player names (participants, rankings, player details) are out
  of scope; noted as backlog.
