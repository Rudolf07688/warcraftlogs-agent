# Feature Specification: Shared UI Component Adoption

**Feature Branch**: `010-shadcn-ui-adoption`

**Created**: 2026-10-11

**Status**: Draft

**Input**: User description: "Use your recommendations above to write the spec for the next update" — the recommendations being the component-by-component comparison of the app's hand-built controls against the project's already-configured shared component library (buttons, form fields, selects, dialogs, confirmations, tabs, tables, status messaging).

## Overview

The app's screens are built from individually styled native controls: the sign-in,
accept-invitation and reset-password forms each style their own inputs and buttons; the
admin page styles its tables, forms and action buttons inline; the profile page builds its
own tab strip and its own guide-viewer overlay; the chat shell uses a native dropdown for
the model picker and raw buttons in the header, sidebar and follow-up chips. The project
has a shared component library configured but not yet used.

The visible consequences today are (a) the same control looks slightly different on each
screen, (b) two interactions are weaker than they should be — the guide viewer overlay does
not trap focus, close on Escape or lock background scrolling, and disabling a user relies on
the browser's blocking confirmation box — and (c) every new screen re-invents the same
styling. This update replaces the hand-built controls on the affected screens with the
shared library's equivalents, keeping the existing dark-gold look and the themed chat
elements (spell cards, cast bars, rune spinner, ambient effects, message renderer, charts)
untouched.

## Clarifications

### Session 2026-10-11

- Q: Should the authentication and admin pages keep their separate neutral/indigo palette or adopt the dark-gold chat theme? → A: Re-theme them to the dark-gold theme so the whole app shares one palette.
- Q: Which destructive actions require the in-app confirmation dialog? → A: Every irreversible delete: disable user, delete conversation, remove friend, remove guild. Revoke invitation stays immediate (re-inviting undoes it).
- Q: Native dropdowns or the library's custom pop-up list? → A: Native dropdowns with the shared appearance, on every screen; the custom pop-up list is a non-goal.
- Q: Is the P5 chat-shell polish (collapsible sidebar sections, follow-up and boss-focus chips) in this update? → A: Out of scope; removed from this update and noted as a follow-up.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consistent forms and buttons everywhere (Priority: P1)

A player signs in, accepts an invitation or resets a password; an admin creates an
invitation; a player edits their characters, friends and guild on the profile page; and
everyone uses the chat header (model picker, PDF, Admin, Sign out) and the composer. On
every one of these screens the text fields, dropdowns, labels, validation messages and
buttons look and behave the same: same sizing, same focus ring, same disabled and
loading appearance, same primary/secondary/destructive emphasis.

**Why this priority**: This touches the most screens and removes the most duplicated
styling, with no change to what any control does. It is the foundation the other stories
build on and is independently shippable.

**Independent Test**: Open the sign-in, accept-invitation, reset-password, admin and
profile pages plus the chat shell side by side. Every text field, dropdown, label, error
message and button is visually identical in kind across pages, and every existing flow
(sign in, invite, reset, add friend, change role, pick a model, send a message) still
completes.

**Acceptance Scenarios**:

1. **Given** any of the three authentication pages, **When** the user submits invalid
   input, **Then** the error appears in the same position and style under the field (or
   under the form) as on the other two pages, and the submit button shows the same
   disabled/busy state.
2. **Given** the chat header, **When** a turn is streaming, **Then** the model picker and
   action buttons show the shared disabled appearance and cannot be activated.
3. **Given** the profile Characters tab, **When** the user changes a friend's raid role,
   **Then** the role dropdown behaves exactly as before (same options, immediate save) and
   matches the model picker's look.
4. **Given** the composer, **When** the user presses Enter, **Then** the message is sent;
   Shift+Enter inserts a newline; the Send button is disabled while the field is empty or
   a turn is streaming — unchanged from today.
5. **Given** any page, **When** a keyboard-only user tabs through it, **Then** every
   field and button is reachable in reading order and shows a visible focus indicator.

---

### User Story 2 - Accessible dialogs and in-app confirmations (Priority: P2)

A player opens a class guide from the profile page in a dialog that behaves like a proper
modal: focus moves into it, Tab stays inside it, Escape closes it, the page behind does not
scroll, and focus returns to the guide card afterwards. Every irreversible delete asks
first through the same in-app confirmation dialog with a clearly destructive action: an
admin disabling a user (which today uses the browser's built-in confirmation box), and a
player deleting a conversation, removing a friend or removing their guild (which today
fire immediately).

**Why this priority**: These are the only two places where the current hand-built
version is functionally weaker, not just inconsistently styled. They are small, isolated
changes with high accessibility value.

**Independent Test**: Open a class guide and verify Escape, focus trapping, scroll lock and
focus return. On the admin page, click Disable on a user and verify an in-app dialog
appears, Cancel does nothing, and Confirm disables the user. In the sidebar, click a
conversation's delete control and verify the same dialog guards it.

**Acceptance Scenarios**:

1. **Given** the Class Guides tab with a ready guide, **When** the user activates View,
   **Then** a dialog opens with the guide title announced, focus inside it, and the
   underlying page not scrollable.
2. **Given** an open guide dialog, **When** the user presses Escape or activates Close or
   clicks the backdrop, **Then** the dialog closes and focus returns to the control that
   opened it.
3. **Given** an open guide dialog whose content is longer than the viewport, **When** the
   user scrolls, **Then** only the dialog content scrolls.
4. **Given** the admin users list, **When** the admin activates Disable on an active user,
   **Then** an in-app confirmation names the user's email and offers Cancel and a visibly
   destructive Disable action; the browser's native confirmation box is never shown.
5. **Given** the confirmation dialog, **When** the admin confirms and the request fails,
   **Then** the dialog closes and the page shows the failure in its standard error
   message area; the user remains enabled.
6. **Given** the sidebar, **When** the user activates a conversation's delete control,
   **Then** a confirmation names the conversation title, Cancel leaves it in place, and
   Confirm deletes it (opening a fresh chat if it was the active one, as today).
7. **Given** the profile Characters tab, **When** the user activates Remove on a friend
   or on the guild, **Then** the same confirmation appears before anything is removed.
8. **Given** the admin invitations list, **When** the admin activates Revoke, **Then**
   the invitation is revoked immediately with no confirmation (re-inviting undoes it).

---

### User Story 3 - Keyboard-navigable profile tabs that keep their state (Priority: P3)

A player on the profile page switches between Characters and Class Guides with the mouse
or with the arrow keys; the selected tab is announced to assistive technology; and any
half-filled form on the Characters tab is still there when they switch back.

**Why this priority**: A contained accessibility improvement on one screen. The state
preservation already exists and must not regress.

**Independent Test**: Start typing a friend's name on Characters, switch to Class Guides
with the right arrow key, switch back with the left arrow key, and confirm the typed text
is still present.

**Acceptance Scenarios**:

1. **Given** the profile page with the Characters tab focused, **When** the user presses
   the right arrow key, **Then** the Class Guides tab becomes selected and focused.
2. **Given** an in-progress identity form on Characters, **When** the user switches to
   Class Guides and back, **Then** the form's typed values are unchanged.
3. **Given** the Class Guides tab is not selected, **When** the page loads, **Then** no
   guide list request is made until the tab is first selected (unchanged from today).

---

### User Story 4 - Admin tables and status messaging (Priority: P4)

An admin reviewing invitations and users sees two well-structured tables with consistent
header, row and action-button styling; load and action failures appear in a standard
alert strip; and statuses (pending, active, disabled, expired) read as consistent badges.
The same badge and alert treatment is used for the profile's guide status pills and for
the chat header's "fallback model list" warning.

**Why this priority**: Mostly a visual and consistency win on an admin-only screen, so it
ranks below the player-facing stories.

**Independent Test**: Load the admin page with at least one invitation and one user.
Tables, badges and the error strip render in the shared style; revoke, resend, disable and
re-enable still work.

**Acceptance Scenarios**:

1. **Given** the admin page, **When** an action fails, **Then** the error appears in a
   dismissible alert strip at the top of the content, styled like every other alert in the
   app.
2. **Given** a user row, **When** rendered, **Then** its status is a badge whose colour
   distinguishes active, disabled and pending-invitation states.
3. **Given** the chat header when model discovery was degraded, **When** rendered,
   **Then** the warning uses the shared badge/alert treatment and keeps its explanatory
   tooltip.

---

### Edge Cases

- A guide dialog is open when the guide list refreshes in the background: the dialog
  stays open with its current content.
- Escape is pressed while a confirmed delete request is in flight: the dialog stays open
  until the request resolves, then closes.
- The active conversation is deleted via the confirmation: the app opens a fresh chat,
  exactly as it does today.
- The user prefers reduced motion: no dialog, tab or collapsible transition animates.
- Narrow (phone-width) viewports: the guide dialog fills the width with a 16px gutter,
  admin tables scroll horizontally rather than overflowing the page, and chips wrap.
- Very long error messages from the server wrap inside the alert strip without pushing
  the layout.
- A dropdown with a single option (one available model) still renders and stays
  selectable.
- Every replaced control must keep its existing accessible name (labels, titles,
  aria-labels) so screen-reader output does not regress.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All text inputs, dropdowns, labels, inline validation messages and buttons
  on the sign-in, accept-invitation, reset-password, admin and profile pages and in the
  chat header and composer MUST be built from the shared component set, not from
  individually styled native elements.
- **FR-002**: Buttons MUST express exactly one of a fixed set of emphases (primary,
  secondary, ghost, destructive) and sizes (default, small, icon); no per-screen button
  styling may remain on the pages in FR-001.
- **FR-003**: All dropdowns (chat model picker, raid role, admin invite role) MUST keep
  native keyboard and mobile behaviour while adopting the shared appearance; the
  library's custom pop-up list MUST NOT be used.
- **FR-004**: The composer MUST keep Enter-to-send, Shift+Enter for newline, and its
  disabled rules (empty text, streaming, disconnected).
- **FR-005**: The class-guide viewer MUST be a modal dialog that traps focus, closes on
  Escape, backdrop click and the Close control, locks background scrolling, and returns
  focus to the opening control.
- **FR-006**: Every irreversible delete MUST require the shared in-app confirmation
  dialog, with Cancel and a visibly destructive confirm action that names the affected
  item: disable user, delete conversation, remove friend, remove guild. Revoke invitation
  and re-enable user remain immediate. The browser's built-in confirmation box MUST NOT
  be used anywhere in the app.
- **FR-007**: The profile tabs MUST support arrow-key navigation, expose the selected
  tab to assistive technology, and keep both tabs' in-progress state when switching.
- **FR-008**: The Class Guides tab MUST continue to defer its first data load until it is
  first selected.
- **FR-009**: Admin invitation and user lists MUST render as shared-style tables with
  status badges; load and action failures MUST render in a shared alert component.
- **FR-010**: Guide status pills on the profile page and the degraded-model warning in
  the chat header MUST use the shared badge treatment and keep their existing tooltips.
- **FR-011**: The app MUST use a single palette, the existing dark-gold theme: the shared
  components MUST take their colours, radius and focus ring from the app's existing theme
  tokens, and any tokens the shared components require that the theme does not yet define
  MUST be added in the same palette. The sign-in, accept-invitation, reset-password and
  admin pages, which today use a separate neutral/indigo palette, MUST be re-themed to
  the dark-gold theme; the neutral/indigo palette is retired.
- **FR-012**: The app MUST NOT introduce a second icon library; shared components that
  require icons MUST use the icon set already in use.
- **FR-013**: Every replaced control MUST retain its existing accessible name and role.
- **FR-014**: Motion added by the shared components MUST respect the user's
  reduced-motion preference.
- **FR-015**: The following MUST remain unchanged: message list and streaming renderer,
  spell cards, cast bars, rune spinner, ambient effects, backend boot overlay, chart
  artifacts, the sidebar drag-resize handle, the sidebar's collapsible Raids and
  Conversations sections, the follow-up question chips and the boss-focus picker.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An audit of the pages in FR-001 finds zero individually styled native
  text inputs, dropdowns or buttons; 100% are instances of the shared set.
- **SC-002**: The browser's built-in confirmation box is shown zero times across all
  admin flows.
- **SC-003**: 100% of dialogs in the app can be opened, operated and closed by keyboard
  alone, and focus returns to the opening control every time.
- **SC-004**: A keyboard-only user can sign in, switch profile tabs, add a friend,
  and disable a user (with confirmation) without using a pointer.
- **SC-005**: After the change, the authentication, admin, profile and chat screens all
  use the dark-gold palette (no neutral/indigo surfaces remain). Side-by-side screenshots
  of the chat and profile screens before and after show the same background, accent and
  text colours, and reviewers spot no regression in the themed chat elements listed in
  FR-015.
- **SC-006**: All existing frontend and backend automated checks pass, and the initial
  page download grows by no more than 10% compared with the current build.
- **SC-007**: No existing user flow (sign in, invite, reset, profile edit, model pick,
  send, follow-up, boss focus, admin actions) changes its number of steps, except the
  four irreversible deletes in FR-006, which gain exactly one confirmation step.

## Assumptions

- The shared component library is the one already configured in the project; this
  update adopts it rather than evaluating alternatives. Only components whose
  dependencies are limited to the library's own helper and headless primitives are in
  scope, so that no second icon library is pulled in (FR-012).
- Dropdowns keep native behaviour (FR-003) because no screen needs search, grouping or
  rich option rendering; a custom pop-up list is a deliberate non-goal.
- The sidebar drag-resize handle and its persisted width are kept as-is; moving them to
  a shared resizable panel is deferred to a later update.
- Chat-specific primitives offered by the library (message, message scroller) are not
  adopted; the existing message renderer and stick-to-bottom behaviour are working and
  out of scope.
- The boot overlay added in the previous update keeps its themed rune spinner rather than
  the library's generic spinner.
- Visual parity is judged against the current dark-gold theme; no light theme is
  introduced. The authentication and admin pages are re-themed to it rather than kept in
  their current neutral/indigo look (see Clarifications).
- No data model, backend endpoint or persistence change is required; this is a
  frontend-only update.
- Stories are independently shippable in priority order.
- Restyling the sidebar's collapsible sections, the follow-up chips and the boss-focus
  chips with the shared set was considered and deferred to a follow-up update; they work
  today and are listed as unchanged in FR-015.
