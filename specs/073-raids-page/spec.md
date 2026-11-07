# Feature Specification: Raids page

**Feature Branch**: `073-raids-page`

**Created**: 2026-11-07

**Status**: Draft

**Input**: Rework the Raids "dropdown" (the sidebar's collapsible raid list) into a Raids page with one tab per tracked raid, show each raid's stored data without a chat, and add an "Analyze this raid" button that starts a new chat. Stories sc-141, sc-143, sc-142 (UI half).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Switch raids with tabs (Priority: P1)

A user opens the Raids page and sees one tab per tracked raid, most recent first. Clicking a tab shows that raid. The address selects the tab, so a link opens a given raid and the back button returns to the previous one.

**Why this priority**: It replaces the dropdown and is the frame for the other two stories.

**Independent Test**: Render the page with three raids, click the second tab, check the address and the shown raid; go back and check the first raid is shown again.

**Acceptance Scenarios**:

1. **Given** three tracked raids, **When** the user opens the Raids entry in the sidebar, **Then** the page shows three tabs, the newest first and selected, and the address names that raid.
2. **Given** the page is open, **When** the user clicks another tab, **Then** that raid's label, date and boss summary show and the address changes to it.
3. **Given** an address naming a raid that is not in the list (or an encoded path segment such as `..%2F`), **When** the page opens, **Then** a "raid not found" message shows and no request is made for it.
4. **Given** no tracked raids, **When** the page opens, **Then** a "No raids tracked yet" message shows.
5. **Given** a phone-width screen (390px), **When** many raids exist, **Then** the tab list scrolls sideways and the page does not.

---

### User Story 2 - See stored raid data (Priority: P1)

Each raid tab shows what is already stored for that raid: its duration, its participants grouped by role, and the user's own characters' parses, so the user can review it without opening a chat.

**Why this priority**: It is the point of the rework ("review it without a chat").

**Independent Test**: Mock the summary call with the contract example; the tab shows the duration, the participant and the parse.

**Acceptance Scenarios**:

1. **Given** a raid with stored data, **When** its tab is shown, **Then** the duration, the participants grouped by role (tank, healer, dps, other) and each of the user's characters with its parses (encounter, difficulty, percentile) show.
2. **Given** the summary is loading, **Then** a loading state shows; **Given** it fails, **Then** an error message with a retry shows.
3. **Given** nothing is stored, **Then** "Nothing stored for this raid yet: analyze it to pull its data" shows.
4. **Given** one part is missing (for example no parses), **Then** the other parts still show.
5. **Given** the raid is not tracked by the caller (404), **Then** the "raid not found" message shows.

---

### User Story 3 - Analyze this raid (Priority: P1)

A button on each raid starts a new chat with the same analyze message that the sidebar raid click sends today.

**Why this priority**: Keeps the one-click investigation now that the sidebar click only navigates.

**Independent Test**: Click the button; a new conversation is created for that report and the analyze message is sent in it, exactly as the previous raid click did.

**Acceptance Scenarios**:

1. **Given** a raid tab, **When** the user clicks "Analyze this raid", **Then** the app leaves the page for the new chat and the analyze message is sent.
2. **Given** the investigation request fails, **Then** the existing error message shows and the user stays put.

### Edge Cases

- A raid label, guild, zone or player name containing HTML or markdown shows as plain text.
- A 300-character name is cut off with an ellipsis and does not break the layout at 390px.
- The raid list changes while the page is open (a raid is tracked): the tabs update.
- The summary of a raid the user switched away from arrives late: it must not show under another tab.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Raids page MUST be reachable at `/app/raids` and `/app/raids/:reportCode`, inside the app shell.
- **FR-002**: The page MUST show one tab per tracked raid, most recent first; the address picks the tab; with no code it selects the newest.
- **FR-003**: The sidebar MUST show a single "Raids" entry with the raid count that opens the page, and MUST NOT start a chat when clicked.
- **FR-004**: Each tab MUST show the raid label, date and boss summary (kills marked) from the raid list.
- **FR-005**: Each tab MUST fetch the raid's stored summary and show duration, participants grouped by role, and the user's characters' parses, with loading, empty, error and not-found states; parts missing on their own MUST NOT hide the others.
- **FR-006**: The report code in a request MUST be percent-encoded, and a code not in the raid list MUST NOT cause a request.
- **FR-007**: "Analyze this raid" MUST start a new chat through the existing investigate-and-send flow (no second implementation).
- **FR-008**: All raid and player text MUST be rendered as text; long names MUST be truncated with CSS.
- **FR-009**: Only one summary is shown at a time; a late answer for another raid MUST be ignored.

### Key Entities

- **Raid**: a tracked report (code, label, date, boss list), already in the raid list.
- **Raid summary**: stored data for one raid (see `contract:raid-summary`): duration, participants with role, the user's characters with parses, when it was fetched.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user reaches any tracked raid's stored data in one click on its tab, with no chat.
- **SC-002**: A user starts a raid analysis chat in one click from the raid's tab.
- **SC-003**: At 390px wide the page has no horizontal scroll and the tab list scrolls sideways.
- **SC-004**: Hostile raid text (HTML, 300 characters) never renders as markup or breaks the layout.

## Assumptions

- The summary endpoint (stream 072) exists with the shape in `contract:raid-summary`; the page never calls WCL itself.
- Portraits are out of scope (stream 075); initials avatars may be used.
- The raid list and the investigate flow stay in the chat shell (App), so the socket and conversation state are shared.
- Participants not tank/healer/dps (role null) are grouped under "Other".
