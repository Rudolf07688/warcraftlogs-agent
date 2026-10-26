# Feature Specification: Participant Resolution

**Feature Branch**: `030-participant-resolution`

**Created**: 2026-10-26

**Status**: Draft

**Input**: User description: "Agent resolves run/raid participants with class and role for profile actions (sc-206)." Design input: `documentation/designs/self-aware-agent/participants-and-confirmation.html`; decisions D5 and D9 in the sprint decisions file.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get who was in a run, with class and role (Priority: P1)

A user points Barnaby at a report (and a fight or M+ run) and asks who was in it. Barnaby returns the real players with name, realm, region, class, spec and role, in a short, compact list that is cheap to keep in the conversation. Pets and NPCs never appear.

**Why this priority**: Every profile action from a run ("add these to my friends") depends on a reliable list of people. Without it nothing else in the feature works.

**Independent Test**: With a faked report response for a raid and for an M+ run, ask for the participants and check each row carries all six fields, the roster has only players, and the output stays within the size budget.

**Acceptance Scenarios**:

1. **Given** a raid report with 40 distinct players and some pets, **When** participants are requested for the whole report, **Then** every player appears once with name, realm, region, class, spec and role, no pet or NPC appears, and the result is at most 6,000 characters.
2. **Given** an M+ report and the keystone fight, **When** participants are requested for that fight, **Then** exactly the 5 players of that key appear, ordered tank, healer, then damage dealers, in at most 1,500 characters, each row at most 120 characters.
3. **Given** a player whose realm is not available in the report data, **When** participants are requested, **Then** the player still appears with realm null rather than being dropped or given a guessed realm.

---

### User Story 2 - Barnaby works out which run "the dungeon" means (Priority: P1)

When the user says "the dungeon" or "the raid", Barnaby finds the run without guessing: a report named in the message wins, then the one run of that kind already discussed in this chat; "last" or "latest" selects the newest stored run; otherwise he asks, listing up to 5 candidates.

**Why this priority**: A wrong guess writes the wrong people into a profile (decision D5). This is the safety rule of the feature.

**Independent Test**: Run the ambiguous case (several stored runs, no chat context, no "last") and confirm Barnaby asks with at most 5 candidates and calls no participant lookup; then confirm each resolved case picks the right run.

**Acceptance Scenarios**:

1. **Given** the message contains a report link, **When** the user asks for the participants, **Then** that report (and fight, if the link names one) is used.
2. **Given** exactly one run of the requested kind was discussed earlier in this chat, **When** the user says "the dungeon", **Then** that run is used.
3. **Given** no run in the chat and several stored runs, **When** the user says "the latest dungeon", **Then** the newest stored run of that kind is used.
4. **Given** no run in the chat, several stored runs and no "last"/"latest", **When** the user says "the dungeon", **Then** Barnaby asks which run, listing at most 5 candidates with date and report identity, and does not fetch participants.
5. **Given** Barnaby knows the user's recent runs, **When** a turn starts, **Then** a compact "Recent runs" summary and report codes on the tracked-raids line are available to him, adding no new request to the log service.

---

### User Story 3 - Filter the roster by class or role (Priority: P2)

The user refines the list in plain words ("except the shaman", "only the healers"). Barnaby applies this to the structured rows, which each carry class and role.

**Why this priority**: It is the owner's motivating example, but it follows once the list exists.

**Independent Test**: On a faked roster, apply "except the shaman" and "only the healers" and verify the expected rows remain.

**Acceptance Scenarios**:

1. **Given** a roster containing one shaman, **When** the user says "except the shaman", **Then** the remaining rows contain no shaman and all others.
2. **Given** a roster with two healers, **When** the user says "only the healers", **Then** only those two rows remain.

---

### Edge Cases

- A report with several M+ keys and no fight id counts as several candidates, never one.
- A player who swapped spec or role during a raid appears once, with the spec they played most.
- An empty roster or a report the user cannot access returns a clear error result, not an empty success.
- A generic "the log" may mean either kind; Barnaby asks if both kinds are candidates.
- A single candidate with no chat context still prompts a one-line confirmation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Given a report code and optionally a fight, the system MUST return the participants with name, realm, region, class, spec and role.
- **FR-002**: The output MUST exclude pets and NPCs and list each player once.
- **FR-003**: Each row MUST be at most 120 characters; an M+ result at most 1,500 characters; a 40-player raid at most 6,000 characters; the result MUST never be truncated.
- **FR-004**: Players with an unknown realm MUST still be listed, with realm null (missing keys in the report data are tolerated).
- **FR-005**: Participant data MUST be fetched through the existing single log-service client and existing report query helper, with no new query and no new cache family.
- **FR-006**: Looking up participants MUST count as report access so the raid is tracked like other report tools.
- **FR-007**: Run resolution MUST follow, in order: report named in message; the one run of that kind in the chat; the newest stored run only on "last"/"latest"; otherwise ask with at most 5 candidates. It MUST never guess silently.
- **FR-008**: Each turn MUST expose to Barnaby a compact "Recent runs" line (up to 5 runs of each kind, newest first, about 600 characters, with report codes and fight ids) and report codes on the tracked-raids line, built from already stored data.
- **FR-009**: Each row MUST carry class and role so the model can filter ("except the shaman", "only the healers") without filter arguments.
- **FR-010**: The new capability MUST be registered with the agent's own tools, not through backend extra groups, and be described to the model with run-resolution guidance.

### Key Entities

- **Participant**: A player in a run: name, realm, region, class, spec, role (tank, healer or dps).
- **Run candidate**: A stored raid or M+ run identified by report code, kind, label, date and (for M+) fight id.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a raid and an M+ run, 100% of returned rows have all six fields and no pet or NPC.
- **SC-002**: Output sizes stay within 120 characters per row, 1,500 for an M+ run and 6,000 for a 40-player raid.
- **SC-003**: In the ambiguous-run test, Barnaby asks instead of fetching in 100% of cases, with at most 5 candidates.
- **SC-004**: Both example filters give the expected roster on faked data.
- **SC-005**: Resolving participants adds no new log-service query types and no extra requests beyond one report request per lookup.

## Clarifications

### Session 2026-10-26

- Q: Unknown realm? -> A: Keep the row with realm null (D12 correction); the profile-proposal validation (029) flags it.
- Q: Spec/role swaps? -> A: One row per player, most-played spec; role matches that spec where possible, else the first group they appear in.
- Q: Single candidate, no chat context? -> A: Ask a one-line confirmation (D5).
- Q: Empty/inaccessible report? -> A: Standard tool error envelope used by other report tools.
- Q: Live response sample? -> A: No live WCL call (agents never read the owner's credentials). Fakes are built from shapes already in the repo, labelled Inferred; the owner verifies live at review.
- Note: SC-003 is model behaviour; it is tested deterministically (preamble lists the candidates, and a prompt-contract test checks the D5 guidance is present), not with a live-model assertion.

## Assumptions

- Barnaby (the model) performs filtering and run-kind interpretation; only the data and the preamble are code.
- Role is taken from the log service's tank/healer/dps grouping; spec is the most-played spec.
- A real player-details response shape is recorded first as the basis for test fakes; if the log service cannot be reached, this is flagged at the plan gate.
- Friends added from a run keep an inferred role (decision D9); writing profile changes is feature 029, not this one.
- Registration in the agent file and the turn-preamble wiring wait until feature 029 has merged.
