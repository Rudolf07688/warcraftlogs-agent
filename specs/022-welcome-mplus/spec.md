# Feature Specification: Welcome Chat with Recent Raids and Mythic+ Runs

**Feature Branch**: `022-welcome-mplus`

**Created**: 2026-10-25

**Status**: Clarified, signed off 2026-10-25

**Input**: User description: "Welcome chat: show at most 6 recent raids and at most 6 recent Mythic+ runs (sc-153). Each list most recent first. With no M+ runs only raids show, with no empty section or error. Each M+ run shows dungeon, key level, date and whether it was timed, in the same style as raid entries. Clicking an M+ run opens a new chat with an M+ review kickoff prompt, as clicking a raid does. M+ data is fetched through the single Warcraft Logs client and its cache, following feature 013's background refresh pattern so the welcome page never waits on Warcraft Logs."

## Context

Feature 013 gave the welcome page a list of the user's most recent raids, up to 20, fetched in the background and stored. A long raid history floods the page, and a player who mostly runs dungeons sees nothing of their Mythic+ play. This feature trims the raid list to the 6 most recent and adds a second list of the user's 6 most recent Mythic+ runs. One click on a run starts a chat that reviews it, the same way a raid click starts an investigation.

## Clarifications

### Session 2026-10-25

- Q: What is one run? -> A: One keystone fight (report plus fight), several per report possible.
- Q: Timed and abandoned? -> A: Timed = completed within the timer; depleted listed as not timed; abandoned not listed.
- Q: Kickoff and title? -> A: Server-owned M+ kickoff with bounded scope, explicit chat title "M+ <dungeon> +<level>" (FR-015, FR-016).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See only my 6 latest raids (Priority: P1)

The welcome page shows at most the 6 most recent raids across the user's own characters, newest first, instead of up to 20.

**Why this priority**: It is the smallest slice and fixes the "flooded with raids" complaint on its own.

**Independent Test**: With more than 6 raids available for the user's characters, open the welcome page and confirm exactly 6 show, newest first.

**Acceptance Scenarios**:

1. **Given** the user's characters have more than 6 recent raids, **When** the welcome page loads, **Then** only the 6 most recent show, newest first.
2. **Given** fewer than 6 raids exist, **When** the page loads, **Then** all of them show.

---

### User Story 2 - See my recent Mythic+ runs (Priority: P1)

Below the raids, the welcome page shows up to 6 of the user's most recent Mythic+ runs, newest first. Each entry shows the dungeon, the key level, the date and whether the key was timed, in the same visual style as the raid entries.

**Why this priority**: This is the new capability the story asks for.

**Independent Test**: Register an own character with recent Mythic+ runs, open the welcome page and confirm the runs list with dungeon, key level, date and timed status.

**Acceptance Scenarios**:

1. **Given** the user's characters have more than 6 recent Mythic+ runs, **When** the welcome page loads, **Then** the 6 most recent show, newest first.
2. **Given** a run was completed within the timer, **When** it is listed, **Then** it is marked timed. A run completed over the timer is marked not timed.
3. **Given** the user's characters have no Mythic+ runs, **When** the page loads, **Then** only the raids section shows, with no empty M+ section, placeholder or error.
4. **Given** the user has Mythic+ runs but no raids, **When** the page loads, **Then** the runs show and the raid section follows the existing no-raids behaviour.
5. **Given** two of the user's characters were in the same run, **When** the list is built, **Then** the run appears once, naming both characters.

---

### User Story 3 - Click a run to review it (Priority: P1)

Clicking a Mythic+ run opens a new chat that starts reviewing that run without further input, as clicking a raid does.

**Why this priority**: It turns the list into a shortcut and matches what raids already offer.

**Independent Test**: Click a run and confirm a new chat opens and the agent starts a Mythic+ review of that run.

**Acceptance Scenarios**:

1. **Given** the welcome page lists runs, **When** the user clicks one, **Then** a new chat opens with a Mythic+ review kickoff prompt naming that run, and the review starts.
2. **Given** a reply is streaming in another chat, **When** the user clicks a run, **Then** the app behaves as it does for a raid click and never mixes the chats.

---

### User Story 4 - Never wait on Warcraft Logs (Priority: P2)

Mythic+ runs are fetched and kept up to date in the background, like raids. Runs already fetched show immediately on later visits.

**Why this priority**: Stories 2 and 3 work without it only by blocking the page, which the app avoids.

**Independent Test**: Open the page twice. The second time, stored runs show at once with no wait. With Warcraft Logs unreachable, stored runs and raids still show.

**Acceptance Scenarios**:

1. **Given** runs were fetched before, **When** the user returns, **Then** they show immediately.
2. **Given** a newer run exists, **When** the background check runs, **Then** it appears at the top without a page reload.
3. **Given** the Mythic+ fetch fails, **When** the page is open, **Then** the raid list and any stored runs are unaffected and no chat is disrupted.

### Edge Cases

- A run was abandoned or never finished: it is not listed. A depleted run (finished over the timer) is listed as not timed.
- The same run appears under several of the user's characters: it is listed once.
- The user removes an own character: runs that only that character took part in are no longer shown.
- Warcraft Logs is unreachable on a first visit: raids and runs show the existing could-not-load state, and the user can still start an ordinary chat.
- A dungeon name is missing from the data: the entry still lists, named after the report's zone (or "Mythic+"). A missing key level means the run isn't finished, so it isn't listed (decision 20).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The welcome page MUST show at most 6 recent raids, newest first. This replaces the previous cap of 20.
- **FR-002**: The welcome page MUST show at most 6 recent Mythic+ runs for the user's own characters, newest first, in a section separate from the raids.
- **FR-003**: Each Mythic+ run entry MUST show the dungeon name, the key level, the date it was run and whether it was timed, and MUST use the same visual style as raid entries.
- **FR-004**: A run in which several of the user's characters took part MUST be listed once, naming those characters.
- **FR-005**: When the user has no Mythic+ runs, the welcome page MUST show no Mythic+ section, no empty state and no error for it.
- **FR-006**: Clicking a Mythic+ run MUST open a new chat and start a Mythic+ review of that run without further input, using a kickoff prompt specific to Mythic+ runs.
- **FR-007**: A run opened from the welcome page MUST appear among the user's conversations, as a raid does.
- **FR-008**: Mythic+ data MUST be fetched in the background through the app's single Warcraft Logs access path, so it shares its caching and fetch persistence. Showing the welcome page MUST never wait on Warcraft Logs when stored data exists.
- **FR-009**: Fetched runs MUST be shown immediately on later visits, and newly found runs MUST appear on an open welcome page without a reload.
- **FR-010**: A failed Mythic+ fetch MUST NOT affect the raid list, stored runs, the page or any chat, and MUST be retryable.
- **FR-011**: Each user's runs MUST be private to that user's account, and MUST reflect the user's current own characters only.
- **FR-013**: A Mythic+ run is one keystone dungeon fight, identified by its report and fight, not a whole report. One report holding several keys lists each key as its own run.
- **FR-014**: A run finished over the timer (depleted) MUST be listed as not timed. A run that was abandoned or never finished MUST NOT be listed. Timed means the keystone was completed within the timer.
- **FR-015**: The chat opened from a run MUST carry the explicit title "M+ <dungeon> +<level>", so it keeps that title and is not renamed by title generation.
- **FR-016**: The Mythic+ kickoff prompt MUST be owned by the server and built the same way as the raid kickoff. It MUST keep a bounded scope: the result against the timer (timed or depleted, and by how much); for each pull or boss segment, the single biggest time loss; deaths (who died, to what, whether avoidable); interrupt coverage; and one headline improvement for the user's character. The agent MUST stay at run and segment level, and go into cast-level detail only where a segment clearly warrants it.
- **FR-012**: The background Mythic+ refresh MUST follow the same limits as the raid refresh: at most one refresh per user at a time, and no more often than the raid refresh interval.

### Key Entities

- **Mythic+ run**: One completed keystone dungeon run. It has a dungeon, a key level, a date, a timed or not-timed result, the report that holds it, and the user's characters who took part.
- **Recent raid**: As in feature 013. Now capped at 6 on display.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With more than 6 raids and more than 6 runs available, the welcome page shows exactly 6 of each, newest first.
- **SC-002**: A user reaches a Mythic+ review of their latest run in 2 clicks or fewer, without leaving the app or pasting a link.
- **SC-003**: For a user with no Mythic+ runs, the welcome page is identical to the raids-only page, with no extra section or error.
- **SC-004**: On return visits, stored runs show within 1 second of opening the app.
- **SC-005**: When Warcraft Logs is unreachable, 100% of stored raids and runs still show and no chat is affected.
- **SC-006**: In a test with several characters, 100% of runs shared by more than one character appear exactly once.
- **SC-007**: Automated tests cover the 6+6 caps and ordering, the no-Mythic+ case with no empty section, dedup across characters, the depleted-versus-abandoned rule, and the kickoff prompt's key phrases and explicit chat title, with Warcraft Logs responses faked.

## Assumptions

- "Recent" means most recent by start time, the same rule the raid list uses.
- Only completed runs count. Timed means finished within the dungeon's timer.
- The kickoff prompt names the report and the run in the same way the raid kickoff names its report (FR-016).
- The raid display cap and the Mythic+ display cap are separate from the depth at which reports are listed from Warcraft Logs, so listing still finds Mythic+ runs.
- Storage of runs follows the feature 013 pattern only if the plan shows it is needed. Fetch persistence (feature 020) and the shared cache already keep the raw data.
- Feature 020's write-through reaches Mythic+ data because the data goes through the same Warcraft Logs client.
- Out of scope: pagination, "show more", filtering by dungeon or key level, and any Mythic+ analysis beyond the kickoff prompt.
