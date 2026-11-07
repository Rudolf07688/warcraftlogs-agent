# Feature Specification: Character portraits from Battle.net

**Feature Branch**: `075-character-portraits`

**Created**: 2026-11-07

**Status**: Draft

**Input**: Stories sc-363 (fetch and cache character portraits) and sc-364 (show them in the UI), epic 362, with the PO's changed AC for sprint 2026-11-07b: portraits come from their own endpoint for the caller's profile characters (not inside the profile responses), cached in Redis only (no migration); shown on the profile's Characters tab, the chat confirmation card and the welcome page's recent raids and runs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See my characters' real portraits on my profile (Priority: P1)

A player opens the profile page. Each of their own characters and friends shows the character's
in-game portrait next to its name. A character with no portrait (not found, private, a region
the game service does not cover, or the service is down) shows the initials in the class
colour, exactly as today. The profile itself appears at once; portraits fill in when they arrive.

**Why this priority**: it is the story's core value and the place every character is listed.

**Independent Test**: with a fake game service that knows one of two characters, the profile
page shows a portrait image for that one and initials for the other; with the service failing,
both show initials and the page still loads.

**Acceptance Scenarios**:

1. **Given** a profile with a character the game service knows, **When** the profile page
   loads, **Then** the character's avatar shows its portrait image.
2. **Given** the game service is down or slow, **When** the profile page loads, **Then** the
   characters render at once with initials and nothing on the page waits for the service.
3. **Given** a portrait was looked up within its freshness window, **When** the player reloads
   the page, **Then** the game service is not asked again.

---

### User Story 2 - Recognise characters in chat cards and recent raids (Priority: P2)

On the chat's confirmation card (a proposed profile change) and on the welcome page's recent
raids and Mythic+ runs, a character that is in the player's profile shows its portrait; others
show initials.

**Why this priority**: recognition at a glance where characters appear outside the profile.

**Independent Test**: render the card and the welcome list with a portrait lookup holding one
character; that row shows the image, the rest initials.

**Acceptance Scenarios**:

1. **Given** a confirmation card for a character in the profile, **When** it renders, **Then**
   the row shows that character's portrait.
2. **Given** a recent raid with one of the player's characters, **When** the welcome page
   renders, **Then** the raid row shows the character's portrait next to the names.
3. **Given** a card for a character not (yet) in the profile, **Then** it shows initials.

---

### Edge Cases

- Realm or name with path or query characters (`/`, `\`, `..`, `?`, `#`, `%2F`, newline,
  unicode): the outbound address keeps a fixed host and path prefix; the name is one encoded
  path segment.
- Stored region outside eu/us/kr/tw (e.g. `cn`, or a host-like value): no outbound request,
  initials shown.
- The service returns an image address that is not https on the game's render host
  (`javascript:`, `data:`, `http:`, another host, a backslash or userinfo trick): treated as no
  portrait.
- The service redirects, sends a huge body, or does not answer in time: no portrait, bounded
  cost, page unaffected.
- The service is down or rate-limiting: a short-lived "unavailable" entry stops a call per page
  load.
- Two workspaces with characters of the same name: each workspace only ever gets portraits for
  characters in its own profile.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST look up a character's portrait from the game's official character
  media service, using the app's own service credentials and the stored region, realm and name.
- **FR-002**: The system MUST serve portraits for the caller's own profile characters (own and
  friends) from a dedicated request, read from the caller's stored profile on the server; it
  MUST NOT accept character names from the request.
- **FR-003**: Portrait results MUST be cached and shared: a found portrait for a day, a "no such
  character / no portrait" for hours, a service failure for minutes; a page load within those
  windows makes no outbound call.
- **FR-004**: Only https image addresses on the game's render host(s) MAY be stored or served;
  anything else becomes "no portrait".
- **FR-005**: Outbound calls MUST use a fixed host per allowed region (eu, us, kr, tw), encode
  realm and name as single path segments, follow no redirects, bound the response size and the
  time taken.
- **FR-006**: The service credentials and access token MUST never appear in logs, errors, cached
  values or responses.
- **FR-007**: Cache keys MUST be derived from a normalised region, realm and name in a form that
  cannot be injected or grow unbounded.
- **FR-008**: The shared avatar MUST show the portrait when one is given and loads, and the
  initials in the class colour otherwise, at the same size (no layout shift), lazily loaded, in
  every theme. Existing callers that pass no portrait MUST render exactly as before.
- **FR-009**: The avatar with portraits MUST be used on the profile's Characters tab, the chat
  confirmation card and the welcome page's recent raids and runs.
- **FR-010**: Without configured service credentials the feature MUST degrade to initials with
  no outbound call.

### Key Entities

- **Portrait entry**: one profile character's id, name, realm, region, class and portrait
  address (or none).
- **Cached portrait**: per region/realm/name, the portrait address or a "none"/"unavailable"
  outcome, with its freshness window.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The profile page renders its characters with no added wait, whatever the game
  service does.
- **SC-002**: Repeated page loads within a day cause at most one outbound lookup per character.
- **SC-003**: Every hostile input listed under Edge Cases ends in "no portrait" or a correctly
  encoded request, proven by one automated test each.
- **SC-004**: Characters with a public portrait show it on all three surfaces after the first
  load.

## Assumptions

- The game service's character-media answer lists images by kind; the small "avatar" image is
  used (the live response shape is confirmed by team-lead's pre-check).
- China (`cn`) is out of scope: a different service; those characters show initials.
- The raids page portrait is a follow-up (the page is rebuilt in parallel by 073); the sidebar
  shows no characters.
- No database change: the cache is the shared Redis already used for Warcraft Logs data.
