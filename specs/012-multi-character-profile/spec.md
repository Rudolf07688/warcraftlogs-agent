# Feature Specification: Multiple Own Characters on the Profile

**Feature Branch**: `012-multi-character-profile`

**Created**: 2026-10-14

**Status**: Draft

**Input**: User description: "add the ability to register more than one character to your profile. This must just be injected into llm prompt so that the model knows what to look for when a reference such as "I" or "me" is made"

## Context

Today a profile holds exactly one "your character" entry, plus any number of friends and one main guild. The assistant receives that one character as standing context and uses it to resolve "I", "me" and "my". Many players raid on more than one character (alts, a second main, a character on another server). Their alts can only be recorded as "friends", so the assistant treats them as other people and does not include them when the user says "how did I do?".

This feature lets the user register several characters as their own. All of them reach the assistant as "the user's characters". It is deliberately narrow: it changes what the profile stores and what the assistant is told. It does not add per-character dashboards or filtering.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Register several characters as my own (Priority: P1)

On the profile page the user can add more than one character as "mine", see them all listed, edit any of them (including the raid role), and remove any of them.

**Why this priority**: Nothing else in this feature can happen until the user can record more than one character. With only this story done, the user's alts are at least stored correctly instead of being recorded as friends.

**Independent Test**: Add three own characters, reload the profile, and confirm all three are listed with their class, spec and role. Edit one, remove one, reload again, and confirm the changes persisted.

**Acceptance Scenarios**:

1. **Given** a profile with one own character, **When** the user adds a second and a third own character, **Then** all three are listed as the user's own characters and persist across reloads.
2. **Given** several own characters, **When** the user changes the raid role of one, **Then** only that character changes and no duplicate is created.
3. **Given** several own characters, **When** the user removes one, **Then** it disappears from the list and the others are unaffected.
4. **Given** an own character is already registered, **When** the user tries to add the same character (same name, server and region) again as their own, **Then** it is rejected with a clear "already added" message.
5. **Given** a character is saved as a friend, **When** the user tries to add it as their own, **Then** it is rejected with a clear message that it is already saved as a friend. The same applies in reverse.
6. **Given** a newly added own character, **When** it is saved, **Then** its class, spec and spec guide are resolved in the background in the same way as for the single character today.
7. **Given** a user who saved one character before this feature, **When** they open the profile after the upgrade, **Then** that character appears as their first own character with its role and guide intact.

---

### User Story 2 - The assistant treats all my characters as "me" (Priority: P1)

When the user says "I", "me", "my" or "how did I do", the assistant knows every character the user has registered as their own. It looks for those characters in the logs it examines.

**Why this priority**: This is the reason for the feature. Without it, storing several characters changes nothing in the answers.

**Independent Test**: Register two own characters. Ask "how did I do?" about a report that contains only the second character. Confirm the assistant finds and discusses the second character without being told its name.

**Acceptance Scenarios**:

1. **Given** two or more own characters, **When** the user asks a first-person question, **Then** the assistant's standing context lists every own character with name, server, region, class, spec and role. The characters are clearly labelled as the user's own and kept separate from friends.
2. **Given** a report in which exactly one of the user's own characters took part, **When** the user asks "how did I do?", **Then** the assistant answers about that character.
3. **Given** a report in which several of the user's own characters took part, **When** the user asks a first-person question, **Then** the assistant either covers each of them, labelled by name, or asks which one the user means. It never silently picks one.
4. **Given** a report in which none of the user's own characters appear, **When** the user asks a first-person question, **Then** the assistant says that none of the user's characters were found in that report rather than guessing.
5. **Given** a profile with no own characters, **When** the user asks a first-person question, **Then** the assistant behaves as it does today without a self character.
6. **Given** own characters exist, **When** the user asks a population-level question unrelated to them, **Then** the assistant does not narrow its answer to the user's characters.

---

### Edge Cases

- **The user has exactly one own character.** The assistant's context and behaviour stay equivalent to today.
- **The user reaches the maximum number of own characters.** Adding another is rejected with a clear message stating the limit.
- **The user removes their last own character.** This is allowed, and the profile then has no own character. That is a valid state.
- **The class or spec of an own character has not been resolved yet.** The character is still listed and passed to the assistant using the details that are known, without empty placeholders.
- **The user has many characters with long spec guides.** The standing context stays within the existing guide size limits. Guide text is shared across characters with the same class and spec rather than repeated.
- **Two own characters have the same name on different servers or regions.** Both are allowed and are distinguished by server and region everywhere they are shown.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to register more than one character as their own, up to a maximum of 10 per profile.
- **FR-002**: Users MUST be able to add, edit (including the raid role) and remove each own character individually. Editing one character MUST NOT affect the others.
- **FR-003**: The system MUST reject a duplicate own character (same name, server and region) with a clear "already added" message.
- **FR-004**: A character MUST NOT be both an own character and a friend at the same time. The system MUST reject the conflicting addition with a message that says where the character is already saved.
- **FR-005**: Each own character MUST keep the attributes the single self character has today: class, spec, raid role (inferred or user-set) and spec-guide status. It MUST be resolved in the background in the same way.
- **FR-006**: An existing single self character MUST become the user's first own character on upgrade, with no data loss and no action required from the user.
- **FR-007**: The assistant's standing context MUST list every own character, clearly labelled as belonging to the user and kept separate from friends and the guild.
- **FR-008**: The assistant's instructions MUST tell it to treat first-person references ("I", "me", "my", "mine") as referring to any of the user's own characters, and to look for all of them in the data it examines.
- **FR-009**: When several of the user's own characters are relevant to a first-person question, the assistant MUST either address each one by name or ask which one is meant. It MUST NOT silently pick one.
- **FR-010**: When none of the user's own characters are found in the data being examined, the assistant MUST say so instead of answering about a different player.
- **FR-011**: With zero or one own character, the assistant's behaviour MUST be unchanged from today.
- **FR-012**: The profile page MUST show all own characters in one "Your characters" section, each with name, server, region, class, spec, role and guide status.

### Key Entities

- **Own character**: A World of Warcraft character the user plays. It has name, server, region, class, spec, a raid role (inferred or user-set) and a spec-guide status. A profile has 0 to 10 own characters.
- **Friend character**: Unchanged. A character the user follows but does not play. It can never be one of the user's own characters at the same time.
- **Player context**: The standing information given to the assistant on each turn. It now carries a list of own characters instead of a single one.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can add a second own character in under 30 seconds from opening the profile page.
- **SC-002**: In a test set of first-person questions about reports where exactly one of the user's own characters appears, the assistant identifies the correct character in at least 9 out of 10 cases without being told the name.
- **SC-003**: When several of the user's own characters appear in a report, the assistant covers all of them or asks which one is meant in 100% of test cases.
- **SC-004**: 100% of profiles that had a self character before the upgrade still have it afterwards, as their first own character with its role and guide preserved.
- **SC-005**: Users no longer need to save their alts as friends. After release, no profile has the same character registered as both an own character and a friend.

## Assumptions

- **The cap is 10.** This covers typical alt counts and keeps the assistant's standing context small. The user did not name a limit.
- **No main or primary character.** All own characters are equal. Order is the order they were added. A "main" flag can be added later if answers need a default.
- **The prompt change is the whole change.** "Injected into the prompt" means no new tools or per-character filtering. The assistant uses the list as context and finds the characters in logs with its existing abilities.
- **Scope stays per profile.** Own characters are scoped the same way the current self character and friends are.
- **Guides are unchanged.** Spec guides continue to come from the shared guide library. Characters with the same class and spec share one guide in the assistant's context.
- **Other features don't depend on a single self character.** The greeting and the tracked raids list do not use it today, so no other features need to change.
