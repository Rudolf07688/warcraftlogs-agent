# Feature Specification: Sidebar & conversations: order, pinning, generated names

**Feature Branch**: `019-sidebar-conversations`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Feature 019 sidebar conversations. Three stories: sc-154 (1pt) move the Conversations section above the Raids section in the left sidebar, both keep their collapse toggles and counts. sc-165 (3pt) pin/unpin a chat from its sidebar entry and from the open chat's header; pinned chats show in a "Pinned" group at the top of the conversation list; state persists server side via a tenant-scoped API that respects tenancy (another tenant's conversation gives not-found); survives reload and re-login. sc-155 (3pt) auto-generate conversation names: after the first complete assistant reply in a conversation that still has its default name (first-message excerpt or "New chat"), the server generates a short title (at most 60 characters, plain text, no quotes or markdown) from the first exchange with a lightweight model through the existing retry/rate-limit helpers; off the chat path, never delays the reply stream, at most once per conversation, on failure or rate limit the first-message title stays and nothing errors to the user; conversations created with an explicit title (raid investigations, recent-raid kickoffs) keep it; the sidebar shows the new title without a manual reload. Backend tests cover generation, once-only, explicit-title rule, failure fallback with the model faked, and pin tenancy."

Shortcut stories: sc-154, sc-165, sc-155 (Team 1, iteration "WCL App Q4 2026").

## Clarifications

### Session 2026-10-25

Answered by the product owner via the scrum master (sprint decisions.md entries 9–13).

- Q: How is the Pinned group ordered? → A: Most recently pinned first.
- Q: Are pins per workspace or per user? → A: Per workspace, like conversations.
- Q: Where does the Pinned group sit? → A: A sub-group inside the Conversations section. It collapses with that section, the section count stays the total, and it is hidden when nothing is pinned.
- Q: What is the sidebar pin control? → A: A pin button on each entry next to delete. It shows on hover or focus, and always shows when the chat is pinned. The chat header gets a pin button too. Product owner addition: both buttons must be keyboard reachable, with an accessible name "Pin chat" / "Unpin chat" and an exposed pressed state.
- Q: Are chats that existed before this feature renamed? → A: No, they keep their names.
- Product owner acceptance point: explicit titles (raid investigations, recent-raid kickoffs) are marked as explicit when the chat is created, so the keep-the-name rule holds for new chats as well as old ones.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conversations first in the sidebar (Priority: P1, sc-154)

A player opens the app and wants to get back to a recent chat. The sidebar lists their
previous conversations directly under the "New chat" and "Profile" buttons, above the
tracked Raids, so the most-used list is the easiest to reach.

**Why this priority**: The smallest change with the most everyday value; it also sets
the section layout that the Pinned group (story 2) builds on.

**Independent Test**: Open the app with at least one conversation and one tracked raid.
The Conversations section appears above the Raids section; each section still collapses
and expands on its own and shows its item count.

**Acceptance Scenarios**:

1. **Given** a player with conversations and tracked raids, **When** the sidebar renders,
   **Then** the Conversations section heading and list appear above the Raids section.
2. **Given** both sections are shown, **When** the player toggles either section,
   **Then** only that section collapses or expands, and both headings keep their counts.
3. **Given** a player with no conversations or no raids, **When** the sidebar renders,
   **Then** the order is the same and each empty section shows its existing empty text.

---

### User Story 2 - Pin important chats (Priority: P2, sc-165)

A player has one or two chats they return to often (for example a long-running
progression analysis). They pin those chats, either from the chat's entry in the sidebar
or from the header of the chat they have open. Pinned chats sit in a "Pinned" group at
the top of the conversation list and stay there across reloads, sign-outs and devices,
until the player unpins them.

**Why this priority**: Direct user value on top of story 1; needs a stored per-chat
state, so it is larger than story 1 but independent of story 3.

**Independent Test**: Pin a chat from the sidebar, reload, sign out and back in: the chat
is still in the Pinned group. Unpin it from the open chat's header: it returns to the
regular list in its normal position.

**Acceptance Scenarios**:

1. **Given** an unpinned chat in the sidebar, **When** the player chooses "Pin" on its
   entry, **Then** the chat moves into a "Pinned" group at the top of the Conversations
   list, and its entry shows it is pinned.
2. **Given** a chat is open, **When** the player uses the pin control in the chat header,
   **Then** the chat is pinned (or unpinned, if it was pinned) and the sidebar updates
   at once; the header control reflects the new state.
3. **Given** pinned chats exist, **When** the player reloads the page or signs out and in
   again, **Then** the same chats are pinned.
4. **Given** a pinned chat, **When** the player unpins it, **Then** it leaves the Pinned
   group and appears in the regular list at its usual position by last activity.
5. **Given** no chats are pinned, **When** the sidebar renders, **Then** no Pinned group
   (and no empty Pinned heading) is shown.
6. **Given** a player in workspace A, **When** a pin or unpin request names a chat that
   belongs to workspace B (or does not exist), **Then** the request is answered as
   not found and workspace B's chat is unchanged.
7. **Given** a pinned chat, **When** the player deletes it, **Then** it disappears from
   the Pinned group like any deleted chat.

---

### User Story 3 - Chats name themselves (Priority: P3, sc-155)

A player starts a chat with a long or vague first message ("hey can you look at last
night's raid for me, the one where we wiped a lot on the last boss"). After the first
answer arrives, the chat's name in the sidebar changes on its own to a short,
descriptive title (for example "Wipes on the last boss, last night's raid"), so old
chats are easy to find later. Chats the app already named on purpose (raid
investigations, recent-raid kickoffs) keep their names.

**Why this priority**: Valuable for finding old chats, but it depends on the agent
module restructure (feature 018) landing first and on a model call, so it comes last.

**Independent Test**: Start a new chat with a long first message. After the first reply
finishes, the sidebar entry's name changes to a short generated title within a few
seconds, without a reload; the reply itself streamed at its usual speed. Start a raid
investigation: its raid name stays.

**Acceptance Scenarios**:

1. **Given** a new chat still named after its first message (or "New chat"), **When**
   the first complete reply is saved, **Then** the app generates a short title from the
   first question and answer and the chat is renamed to it.
2. **Given** a generated title, **Then** it is plain text of at most 60 characters,
   without surrounding quotes, markdown, or line breaks.
3. **Given** a chat whose title was already generated (or attempted), **When** later
   replies complete, **Then** the title is not generated again.
4. **Given** a chat created with an explicit name (raid investigation, recent-raid
   kickoff), **When** its first reply completes, **Then** its name is unchanged.
5. **Given** title generation fails, times out, or is rate-limited, **When** the first
   reply completes, **Then** the chat keeps its first-message name, the player sees no
   error, and the reply and the next turn work as normal.
6. **Given** the chat is open in the sidebar, **When** the title is generated, **Then**
   the sidebar (and the chat header, if it shows the name) shows the new name without a
   manual reload.
7. **Given** the first reply streams, **Then** title generation never delays the reply
   tokens, the "done" signal, or the player's ability to send the next message.

---

### Edge Cases

- A first reply that fails or is interrupted (saved as partial, or an error) does not
  count as the "first complete reply". Generation waits for the first reply that
  completes, and still happens at most once.
- A model reply that is empty, only punctuation, or longer than 60 characters after
  cleaning: an empty result keeps the current name; a long result is cut to 60
  characters at a word boundary where possible.
- Two turns finishing close together (or two browser tabs on the same chat): the title
  is still generated at most once.
- The player closes the tab or the socket drops before the title is generated: the
  title is still saved; the sidebar shows it the next time the list loads.
- The player deletes the chat while its title is being generated: nothing errors and
  nothing is recreated.
- Chats that existed before this feature: they keep their current names (their first
  reply is long past).
- Pinning an already-pinned chat (or unpinning an unpinned one) is harmless and leaves
  it in that state.
- Pinning or unpinning does not change a chat's position by last activity in the
  regular list.
- The player is not signed in, or the request lacks the cross-site protection token:
  the pin request is refused, as with deleting a chat.

## Requirements *(mandatory)*

### Functional Requirements

**Sidebar order (sc-154)**

- **FR-001**: The sidebar MUST show the Conversations section above the Raids section,
  both below the "New chat" and "Profile" buttons.
- **FR-002**: Each section MUST keep its own collapse/expand toggle, its item count, and
  its empty-state text.

**Pinning (sc-165)**

- **FR-003**: Players MUST be able to pin and unpin a chat from its sidebar entry.
- **FR-004**: Players MUST be able to pin and unpin the open chat from the chat header;
  the header control MUST show the current pin state.
- **FR-004a**: Both pin controls (sidebar entry and chat header) MUST be keyboard
  reachable and operable (Tab to focus, Enter or Space to toggle). They MUST have the
  accessible name "Pin chat" when the chat is unpinned and "Unpin chat" when it is
  pinned, and they MUST expose their pressed state to assistive technology (pressed =
  pinned). A sidebar pin control that is visually hidden until hover MUST become
  visible when it has keyboard focus.
- **FR-005**: Pinned chats MUST appear in a "Pinned" group at the top of the
  Conversations list; the rest follow in the existing order (most recent activity
  first). No Pinned group is shown when nothing is pinned.
- **FR-006**: Within the Pinned group, chats MUST be ordered by when they were pinned,
  most recently pinned first.
- **FR-007**: The pin state MUST be stored on the server per chat, so it survives
  reloads, sign-out/sign-in and other devices of the same workspace.
- **FR-008**: Pinning and unpinning MUST be scoped to the player's workspace: a request
  for a chat outside the workspace (or a missing chat) MUST be answered as not found
  and MUST NOT change any data. It MUST require a signed-in session and the same
  cross-site request protection as other changing requests.
- **FR-009**: Pinning or unpinning MUST NOT change the chat's last-activity time, so the
  regular list order does not shift.
- **FR-010**: The conversation list the client receives MUST include each chat's pin
  state, so the sidebar can render the Pinned group from one list request.
- **FR-011**: The stored schema change MUST be reversible: applying and rolling back the
  change both work on a database with existing chats, and existing chats start unpinned.

**Generated names (sc-155)**

- **FR-012**: After the first complete reply in a chat whose name is still a default
  (the first-message excerpt the app sets today, or "New chat"), the system MUST
  generate a short title from the first user message and that reply, and rename the
  chat to it.
- **FR-013**: A generated title MUST be plain text, at most 60 characters, with no
  surrounding quotes, no markdown, and no line breaks. An empty result after cleaning
  MUST leave the current name unchanged.
- **FR-014**: Generation MUST use a lightweight model and go through the app's existing
  model retry and rate-limit handling (reused, not changed).
- **FR-015**: Generation MUST run after the reply is saved and the "done" signal is
  sent, outside the reply stream: it MUST NOT delay the reply, the "done" signal or the
  next turn, and the next turn MUST NOT cancel it.
- **FR-016**: Generation MUST happen at most once per chat, enforced by the stored data
  (not only in memory), so restarts, several app instances and concurrent turns cannot
  run it twice for one chat.
- **FR-017**: If generation fails for any reason (error, timeout, rate limit, chat
  deleted meanwhile), the chat MUST keep its current name, the player MUST see no error,
  and the system MUST NOT retry it later.
- **FR-018**: Chats created with an explicit name (raid investigations, recent-raid
  kickoffs, or any future caller that names a chat on creation) MUST keep that name.
  The chat MUST be marked as explicitly named at the moment it is created, by the one
  shared creation path every naming caller goes through, so the rule holds for new chats
  and not only for pre-existing ones. Automated tests MUST cover each kind of naming
  caller: creating a chat with a name through the conversations API, investigating a
  tracked raid, and investigating a recent raid from the welcome page.
- **FR-019**: When a title is generated while the player's chat connection is open, the
  client MUST be told, and the sidebar (and header, where shown) MUST show the new name
  without a manual reload. If the connection is gone, the name appears the next time the
  list loads.
- **FR-020**: Chats that existed before this feature MUST keep their names.

**Quality**

- **FR-021**: Automated backend tests MUST cover: pinning and unpinning, the pin order,
  the not-found answer for another workspace's chat, the schema change and its rollback
  (including that a chat created after the change starts as default-named, or as
  explicitly named when created with a name), title generation with the model faked,
  the once-only rule, the explicit-name rule for each naming caller (FR-018), and the
  failure/rate-limit fallback.

### Key Entities

- **Conversation (chat)**: an existing per-workspace record with a name, model and
  activity times. Gains a **pinned time** (empty when not pinned; set when pinned,
  which also orders the Pinned group) and a **name origin** that tells a default name
  (eligible for generation) from an explicit one (never replaced) and from one already
  generated or attempted (never generated again).
- **Title-updated notice**: a message to the open chat client that a chat's name has
  changed, carrying the chat and its new name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every sidebar render, the Conversations section is above the Raids
  section, and both sections still collapse and show counts.
- **SC-002**: A player can pin or unpin a chat in one action from either the sidebar or
  the chat header, and the sidebar reflects it in under 1 second.
- **SC-003**: 100% of pinned chats are still pinned after a reload and after signing out
  and in again.
- **SC-004**: 0 pin requests against another workspace's chat change data; each is
  answered as not found.
- **SC-005**: For a new chat with a default name, the generated name appears in the
  sidebar within 10 seconds of the first reply finishing, with no reload.
- **SC-006**: The time from sending a message to the end of the reply is unchanged by
  this feature (title generation adds no wait before "done" or before the next turn).
- **SC-007**: No chat is ever renamed by generation more than once, and 0 explicitly
  named chats are renamed.
- **SC-008**: When the title model is unavailable or rate-limited, 0 errors reach the
  player and the chat keeps its first-message name.

## Assumptions

- The pin feature has no limit on the number of pinned chats; a player typically pins a
  handful.
- Pins are per workspace (like the conversations themselves), not per individual user
  within a shared workspace (confirmed, Clarifications).
- The Pinned group is part of the Conversations section (it collapses with it) and the
  section count stays the total number of chats (confirmed, Clarifications).
- The generated title is in the language of the player's first message.
- There is no manual rename feature today; renaming by hand is out of scope.
- "Lightweight model" means the same kind of fast, cheap model the app already uses for
  follow-up suggestions, independent of the chat's own model.
- sc-155 depends on feature 018 (agent module restructure) being merged first; sc-154
  and sc-165 do not.
- The existing first-message excerpt naming (first 60 characters of the first message)
  stays as the immediate name; generation replaces it only after the first reply.
