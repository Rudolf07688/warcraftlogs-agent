# Feature Specification: Onboarding to profile setup

**Feature Branch**: `074-onboarding-profile-setup`

**Created**: 2026-11-07

**Status**: Draft

**Input**: Stories sc-166 "Onboarding: send new accounts to profile setup (skippable)" and sc-167
"Onboarding: main class/spec and main content selector" (epic 162), plus the chore sc-514
(profile-change schema developer notes, done separately on this branch).

## Clarifications

### Session 2026-11-07

Answered by the developer (autonomous team); each is a board decision `scope:074:<topic>`.

- Q: What makes an account "new"? → A: State, not an event: the workspace has no own
  characters and has never skipped the prompt. Workspaces that exist at rollout are marked as
  skipped, so only accounts created afterwards see it.
- Q: What closes the prompt? → A: "Skip for now", or having at least one own character (seen on
  the next load). Saving the main selector alone does not close it.
- Q: Selector rules? → A: Class may be set alone; a spec needs a class and must be one of its
  specs; content is independent. A save replaces all three values (null clears).
- Q: Sign-in redirect? → A: Only when onboarding is pending AND the destination is the chat
  home; any other destination is honoured if it is a safe internal path, else the chat home.
- Q: Where are the settings kept? → A: On the workspace's own record (one per workspace), read
  and written only by the session's workspace id; no new table.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - New accounts land on profile setup, and can skip it (Priority: P1)

A player who has just activated their account (by accepting an invitation) lands on their
profile page instead of the chat. A welcome prompt at the top asks them to add at least one of
their characters. They can add one, or skip; either way the rest of the app stays fully usable,
and once skipped the prompt does not come back.

**Why this priority**: Without it, new players start in an empty chat and the app does not know
who they play. It is the entry point the selector (story 2) hangs off.

**Independent Test**: Accept an invitation; the browser lands on the profile page with the
welcome prompt. Skip it; reload; the prompt is gone and the chat is reachable.

**Acceptance Scenarios**:

1. **Given** a valid invitation, **When** the player sets a password and activates the account,
   **Then** they land on the profile page with the welcome prompt shown.
2. **Given** the welcome prompt is shown, **When** the player chooses "Skip for now", **Then**
   the prompt closes, and it is not shown again on any later visit or sign-in.
3. **Given** the welcome prompt is shown, **When** the player goes back to the chat without
   doing anything, **Then** the chat works normally (nothing is blocked).
4. **Given** a workspace that has no own characters and has never skipped the prompt (for
   example the operator-created first admin), **When** the player signs in without a specific
   destination, **Then** they land on the profile page with the welcome prompt.
5. **Given** a workspace with at least one own character, or one that skipped the prompt,
   **When** the player signs in, **Then** they go where they were going (the chat by default)
   and no prompt is shown.

---

### User Story 2 - Pick a main class, spec and content (Priority: P2)

On the profile page (and inside the welcome prompt) the player picks their main class, then
optionally one of that class's specs, and their main content: Raid, Mythic+ or both. The choice
is saved to their profile and shown again on the next visit.

**Why this priority**: It lets later features (sc-168 onwards) tailor guides and answers. Saving
it is this story's whole promise; using it is out of scope.

**Independent Test**: Pick "Paladin / Holy / Both", save, reload: the same values are shown.

**Acceptance Scenarios**:

1. **Given** the profile page, **When** the player picks a class, a spec of that class and a
   content choice and saves, **Then** the values are stored and shown again after a reload.
2. **Given** a saved main class, **When** the player clears it, **Then** class and spec are
   unset.
3. **Given** a request with a class or spec not in the app's class/spec roster (wrong case,
   trailing space, a spec of another class, a very long string), **When** it reaches the
   server, **Then** it is rejected and nothing is stored.

---

### Edge Cases

- A redirect destination after sign-in or activation that points off-site (`//evil.example`,
  `/\evil.example`, `javascript:…`) is never followed; the player goes to a fixed internal page.
- A save request that names another workspace or character changes nothing outside the
  caller's own workspace.
- A spec without a class is rejected; changing the class clears a spec that no longer fits.
- Existing workspaces at rollout are not "new": they never see the welcome prompt.
- If the onboarding state can't be read at sign-in, the player goes where they were going.
- A player who adds a character while the prompt is open: the prompt is gone on the next visit.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Activating an account by invitation MUST take the player to the profile page.
- **FR-002**: The profile page MUST show a welcome prompt while the workspace's onboarding is
  pending: it has no own characters and has never skipped the prompt.
- **FR-003**: The prompt MUST ask for at least one character, include the main selector
  (FR-006), and offer "Skip for now".
- **FR-004**: Skipping MUST be stored for the workspace on the server, so the prompt never
  comes back on any device; skipping never blocks any part of the app.
- **FR-005**: Signing in with onboarding pending and no specific destination (the chat home)
  MUST go to the profile page; a specific destination is honoured. Destinations are only ever
  internal paths of the app.
- **FR-006**: The player MUST be able to set and clear a main class, a main spec (only one of
  the main class's specs) and a main content (raid, mplus, both, or unset).
- **FR-007**: The server MUST accept only exact class and spec values from the app's one
  class/spec roster, and content only from raid / mplus / both / unset; anything else is
  rejected with a validation error and nothing is stored.
- **FR-008**: The workspace is taken from the session only; the request body can't name it.
- **FR-009**: Existing workspaces at rollout MUST be treated as already onboarded.
- **FR-010**: The profile's existing responses and calls stay backward compatible (additive).

### Key Entities

- **Workspace profile settings**: per workspace: main class, main spec, main content, and when
  the welcome prompt was skipped (unset while not skipped).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of invitation activations end on the profile page with the prompt shown.
- **SC-002**: After one skip, the prompt is shown 0 times on later loads and sign-ins.
- **SC-003**: Every out-of-roster class/spec/content value tried is rejected with nothing stored.
- **SC-004**: A saved main class/spec/content is shown unchanged after a reload.

## Assumptions

- "New account" is decided by state, not by a one-off event: no own characters and never
  skipped. This covers invitation activation and the operator-created first admin's first
  sign-in, and an invitee who closed the tab before reaching the profile page.
- One user per workspace (v1), so the settings live with the workspace like the rest of the
  profile.
- The roster is the live class/spec roster with the static fallback (feature 015).
- Using the main class/spec/content in guides and answers is out of scope (sc-168, later).
