# Feature Specification: Welcome Page with My Recent Raids

**Feature Branch**: `013-welcome-recent-raids`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Phase 6 of todo.txt: Welcome page. Background fetch of your character's most recent raids. Must be stored since it won't change. Clicking on one opens up a new chat."

## Context

Today, signing in drops the user into an empty chat with a Barnaby greeting. The only raids the app shows are the ones the user has already asked about (the tracked raids in the sidebar). To look at last night's raid, the user has to find the report on Warcraft Logs, copy its link and paste it into a chat.

The profile already knows the user's own characters (feature 012). Warcraft Logs knows which raids those characters were logged in. This feature joins the two. A welcome page lists the user's most recent raids, fetched in the background and stored. One click on a raid starts a new chat that investigates it.

Raid logs do not change once a raid is over, so the details of each fetched raid are stored and never fetched again. Only the question "has a newer raid appeared?" needs to be asked again.

**Side mission (performance):** the feature also moves all Warcraft Logs access to non-blocking calls that can be cancelled, and gives background work its own lane separate from chat (see User Story 4). The welcome page's new Warcraft Logs calls are built on that foundation from the start. Source: `qa-reports/2026-10-16/performance.md`, PERF-201 and PERF-211.

## Clarifications

### Session 2026-10-16

- Q: Which performance improvement from the 2026-10-16 QA report rides alongside this feature? → A: Option A. A native async Warcraft Logs client (PERF-201) plus separate interactive and background lanes (PERF-211).
- Q: How should the background refresh be coordinated across restarts and multiple server instances? → A: Option A. The per-user refresh record is coordinated in the database. An atomic claim makes it the lock, and a run left stale by a crash or restart is reclaimed after a timeout.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See my recent raids when I arrive (Priority: P1)

When the user opens the app, they land on a welcome page. It lists the most recent raids their own characters took part in, newest first. Each entry shows enough to recognise the raid at a glance: raid name, date and time, difficulty, which of the user's characters was there, and how the night went (bosses killed versus pulled).

**Why this priority**: This is the core of the feature. Without it there is nothing to click. Even on its own it is useful, because the user sees their raid history without leaving the app.

**Independent Test**: Register an own character that has public logs. Open the app and confirm the welcome page lists that character's recent raids, newest first, with name, date and time, difficulty, character and kill count.

**Acceptance Scenarios**:

1. **Given** a user with at least one own character that has recent public logs, **When** they open the app, **Then** the welcome page shows that character's most recent raids, newest first.
2. **Given** a user with several own characters, **When** the welcome page loads, **Then** raids from all of them appear in one list, and each entry names the character (or characters) of the user's who took part.
3. **Given** two of the user's own characters appear in the same raid report, **When** the list is built, **Then** that raid appears once, naming both characters.
4. **Given** the user has already visited the welcome page before, **When** they return, **Then** the previously fetched raids appear immediately, without waiting for Warcraft Logs.

---

### User Story 2 - Click a raid to start investigating it (Priority: P1)

Clicking a raid on the welcome page opens a new chat in which Barnaby investigates that raid straight away, in the same way as clicking a tracked raid in the sidebar does today.

**Why this priority**: This turns the list from a display into a shortcut. It removes the find-copy-paste step that the feature exists to remove.

**Independent Test**: Click any raid on the welcome page. Confirm a new chat opens, the investigation begins without the user typing anything, and the chat is about the clicked raid.

**Acceptance Scenarios**:

1. **Given** the welcome page lists raids, **When** the user clicks one, **Then** a new chat opens and an investigation of that raid starts without further input.
2. **Given** the user started a chat from a welcome-page raid, **When** they look at the sidebar, **Then** that raid now appears among their tracked raids and the new chat appears among their conversations.
3. **Given** a reply is still streaming in another chat, **When** the user clicks a raid, **Then** the app behaves as it does today for starting an investigation during a stream. It never mixes the two chats.

---

### User Story 3 - Stored raids, background refresh (Priority: P2)

Raid details are fetched once and stored for good. In the background, the app checks whether the user's characters have newer raids and adds any it finds. The user never waits on a blank page for this, and already-stored raids are never fetched again.

**Why this priority**: Stories 1 and 2 work without this by fetching each time. Storage makes the page instant, survives restarts and keeps Warcraft Logs usage low. It is a stated requirement, but it improves rather than enables the feature.

**Independent Test**: Load the welcome page once. Restart the app and load it again. Confirm the raids appear immediately and that no raid already stored is requested from Warcraft Logs again. Then log a new raid for the character, revisit, and confirm the new raid is added at the top.

**Acceptance Scenarios**:

1. **Given** raids were fetched before, **When** the app restarts and the user returns, **Then** the stored raids are shown immediately.
2. **Given** a raid is already stored, **When** the background check runs, **Then** that raid's details are not requested from Warcraft Logs again.
3. **Given** a character has a newer raid than any stored, **When** the background check runs, **Then** the new raid is added and appears at the top of the list without the user reloading the page.
4. **Given** a background check is already running or ran very recently for this user, **When** the user opens the welcome page again, **Then** no additional check is started.
5. **Given** the user adds a new own character on the profile page, **When** they next open the welcome page, **Then** that character's recent raids are fetched and merged into the list.

---

### User Story 4 - Side mission: responsive, cancellable Warcraft Logs access (Priority: P2)

Today every Warcraft Logs lookup is a blocking call run on a worker thread. A turn the user abandons keeps its lookups running for up to 60-90 seconds, holding shared capacity that other users need. The worker threads also slow down reply streaming for everyone in the process. All Warcraft Logs access moves to non-blocking, cancellable calls. Work is split into two lanes: interactive (chat) and background (guides, patch lookups, welcome-page refreshes). Background work can never crowd out chat.

**Why this priority**: The welcome page's background refresh adds a new and potentially large stream of Warcraft Logs calls; a user with 10 characters triggers 10 or more lookups. Without lanes, that refresh competes directly with chat, which this spec forbids. Building the new calls on the async client from the start avoids building them twice. The change is not needed to show the welcome page, so it ranks below Stories 1 and 2.

**Independent Test**: Start a tool-heavy turn and abandon it. Confirm its outstanding Warcraft Logs lookups stop within a few seconds and free their capacity. Separately, trigger a welcome-page refresh for a user with many characters while another user's turn is running tools. Confirm the chat turn's lookups are not delayed by the refresh, and that reply streaming stays smooth throughout.

**Acceptance Scenarios**:

1. **Given** a turn is running Warcraft Logs lookups, **When** that turn is cancelled or abandoned, **Then** its lookups stop and release their share of Warcraft Logs capacity within 5 seconds.
2. **Given** background work (a welcome-page refresh, a guide build) is using Warcraft Logs, **When** a chat turn needs a lookup, **Then** the chat lookup goes ahead without waiting for background work to finish. Background work only ever uses its reserved share of capacity.
3. **Given** several turns are running tool-heavy lookups at once, **When** replies are streaming, **Then** streaming stays smooth, with no noticeable stalls caused by Warcraft Logs work.
4. **Given** the same Warcraft Logs data is requested by several callers at once, **When** the lookups run, **Then** only one request goes to Warcraft Logs and every caller gets the result, as today.
5. **Given** the migration is complete, **When** any existing feature that uses Warcraft Logs is exercised (chat tools, guides, raid metadata, investigations, the command-line tool), **Then** it returns the same results as before.

---

### Edge Cases

- **No own characters registered.** The welcome page explains that recent raids appear once the user adds their characters and links to the profile page. The rest of the app works as usual.
- **Own characters have no public logs.** The page says that no recent raids were found for the user's characters, instead of showing an empty space or a spinner that never ends.
- **First visit, nothing stored yet.** The page shows a clear loading state while the first fetch runs, then fills in. The user can still start a normal chat meanwhile.
- **Warcraft Logs is unavailable or rate-limited.** Stored raids are still shown. A quiet notice says the list could not be refreshed. If nothing is stored yet, the page says raids could not be loaded and offers a retry. The rest of the app keeps working.
- **A raid is still in progress (a live log).** The raid can be listed. Its details are not treated as final until the raid has ended, so a later check completes them.
- **The user removes an own character.** That character's raids disappear from the welcome list, unless another of the user's characters was in the same raid.
- **A character is renamed or transferred.** It is treated as a different character, as elsewhere in the app. Raids stored under the old identity are no longer shown.
- **A raid has no boss kills (wipes only, or trash only).** It is still listed and shown as "0 of N bosses killed", or simply without a kill count if there were no boss pulls.
- **Many alts with many raids.** The list stays bounded to the most recent raids overall, not the most recent per character.
- **Two users have the same character registered.** Each user sees the raid on their own welcome page. Neither can see the other's list.
- **A background refresh is mid-flight when chat demand spikes.** The refresh slows down or waits. It is never cancelled outright, and it never delays chat lookups.
- **A Warcraft Logs lookup hangs.** It times out, its capacity is released, and the caller gets a clear failure. For chat this is a tool error the agent can recover from. For a refresh the stored list stays as it was (FR-015).
- **The server restarts or crashes mid-refresh.** Raids already stored are kept. The interrupted refresh is reclaimed after the stale timeout and runs again on the user's next visit. The welcome page never shows "refreshing" forever.
- **The same user opens the app on two devices served by different instances.** Only one refresh runs. Both pages pick up the new raids when it finishes.
- **A cancelled lookup was shared with another caller.** Cancelling one caller does not cancel the shared request for the others still waiting on it.

## Requirements *(mandatory)*

### Functional Requirements

**Welcome page**

- **FR-001**: The app MUST show a welcome page when the user arrives with no chat open. This includes right after signing in.
- **FR-002**: The user MUST be able to return to the welcome page at any time from the main navigation.
- **FR-003**: The welcome page MUST still let the user start an ordinary new chat, as they can today.
- **FR-004**: The welcome page MUST list the user's most recent raids across all of their own characters in one list, newest first, up to 20 raids.
- **FR-005**: Each raid entry MUST show the raid (zone) name, the date and time it started, its difficulty when known, which of the user's characters took part, and bosses killed out of bosses pulled when there were boss pulls.
- **FR-006**: A raid report in which several of the user's characters appear MUST be listed once, naming each of those characters.
- **FR-007**: The welcome page MUST show a distinct, clear state for each of: no own characters registered, loading for the first time, no raids found, and could not load.

**Starting a chat from a raid**

- **FR-008**: Clicking a raid entry MUST open a new chat and start an investigation of that raid without further input, using the same kickoff as the existing one-click investigation of a tracked raid.
- **FR-009**: A raid investigated from the welcome page MUST become a tracked raid, and its chat MUST appear among the user's conversations, exactly as if the user had investigated it any other way.

**Fetching and storage**

- **FR-010**: The system MUST fetch the user's recent raids in the background. Showing the welcome page MUST never wait on Warcraft Logs when stored raids exist.
- **FR-011**: The system MUST store fetched raids durably so they survive restarts and are shown immediately on later visits.
- **FR-012**: Once a raid has ended and its details are stored, the system MUST NOT request that raid's details from Warcraft Logs again.
- **FR-013**: The system MUST check for newer raids for the user's own characters at most once every 15 minutes per user. It MUST check when the user arrives and the last check is older than that, and when a new own character has been added since the last check.
- **FR-014**: Newly found raids MUST appear on an open welcome page without the user reloading it.
- **FR-015**: A failed background fetch MUST NOT affect the stored list, block the page, or disrupt any chat. The user MUST be able to retry.
- **FR-025**: At most one refresh per user MUST run at a time, across all server instances. Which instance runs it MUST be decided by an atomic claim on the user's durable refresh record, not by in-memory state.
- **FR-026**: A refresh MUST always end in a recorded outcome, succeeded or failed, even when it errors or times out. A refresh that a crash or restart left marked as running MUST become claimable again once it is older than a stale timeout (default 5 minutes). No refresh may remain stuck.
- **FR-016**: The welcome list MUST reflect the user's current own characters. Raids that only removed characters took part in MUST NOT be shown.

**Scoping**

- **FR-017**: Each user's recent-raid list MUST be private to that user's account (tenant). No user can see another user's list, even when they have registered the same character.

**Side mission: async Warcraft Logs access (PERF-201, PERF-211)**

- **FR-018**: All Warcraft Logs access from the server MUST use non-blocking, cancellable calls. No Warcraft Logs request may run on a worker thread or block the server's event loop.
- **FR-019**: Cancelling or abandoning the work that requested a Warcraft Logs lookup MUST stop that lookup and release its share of capacity. A shared in-flight lookup MUST continue for as long as any caller still waits on it.
- **FR-020**: Warcraft Logs capacity MUST be split into an interactive lane (chat tool calls) and a background lane (guides, patch lookups, welcome-page refreshes, other non-chat work). The background lane MUST have a hard cap below total capacity, and MUST yield to queued interactive work.
- **FR-021**: Every Warcraft Logs lookup MUST have a timeout. A timed-out lookup MUST release its capacity and surface as a recoverable error to its caller.
- **FR-022**: Existing Warcraft Logs protections MUST be preserved: response caching, merging duplicate concurrent requests into one, the overall concurrency cap and rate-limit handling. Cached data MUST NOT be shared mutably between callers.
- **FR-023**: Every existing Warcraft Logs-backed behaviour MUST return results equivalent to today's after the migration. This covers chat tools, guide resolution, raid metadata capture, investigations and the standalone command-line tool.
- **FR-024**: The welcome page's recent-raid fetches MUST run in the background lane.

### Key Entities

- **Recent raid**: A raid report in which at least one of the user's own characters was logged. It has a report identifier, raid (zone) name, start date and time, end time, difficulty, bosses killed and bosses pulled, and whether the raid has ended. Once ended, its details are final.
- **Raid participation**: Links a recent raid to one of the user's own characters that took part. One raid can have several participations from the same user.
- **Refresh record**: One per user. It records when the user's recent raids were last checked, for which set of characters, whether a check is running and since when, and whether the last check succeeded. It limits how often checks run (FR-013). It also acts as the cross-instance lock for a running refresh (FR-025), with stale runs reclaimed (FR-026). The welcome page reads its "running" state to know when to look for new raids.
- **Own character** (from feature 012, unchanged): The source of which characters to look up.
- **Tracked raid** (existing, unchanged): The raids the user has investigated. A welcome-page raid becomes a tracked raid when the user clicks it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On return visits, the welcome page shows the user's stored recent raids within 1 second of opening the app.
- **SC-002**: On a first visit by a user with own characters that have public logs, the recent raids appear within 10 seconds, and the user can start a chat during that time.
- **SC-003**: A user goes from opening the app to an investigation of last night's raid in 2 clicks or fewer, without leaving the app or pasting a link.
- **SC-004**: Across repeated visits, each ended raid's details are requested from Warcraft Logs at most once per user.
- **SC-005**: In a test with several own characters, 100% of raids that more than one of them attended appear exactly once in the list.
- **SC-006**: When Warcraft Logs is unreachable, 100% of previously stored raids are still shown, and no chat is affected.
- **SC-007**: After a turn is cancelled or abandoned, all of its outstanding Warcraft Logs lookups have stopped within 5 seconds, compared with up to 60-90 seconds today.
- **SC-008**: With 4 tool-heavy turns running at once, the longest pause in reply streaming that Warcraft Logs work causes is under 20 ms, down from a worst case of 157 ms today.
- **SC-009**: While a welcome-page refresh for a user with 10 characters runs, chat lookups started at the same time take no longer to begin than when no refresh is running.
- **SC-010**: In a test with two server instances and simultaneous welcome-page visits by the same user, exactly one refresh runs. After a simulated crash mid-refresh, the next visit after the stale timeout completes a refresh successfully.

## Assumptions

- **"Your character" means all own characters.** Feature 012 lets a user have up to 10 own characters, so the list merges them rather than picking one.
- **The welcome page is the "no chat open" view.** It replaces the empty landing chat and lives inside the existing app layout, with the sidebar still visible. Starting a new chat from it keeps today's Barnaby greeting behaviour.
- **20 raids, 15 minutes.** Twenty recent raids covers several weeks of a typical raiding schedule. A 15-minute minimum gap between checks keeps Warcraft Logs usage low while picking up last night's raid on the next visit. Neither number was given by the user.
- **Public logs only.** Only raids visible through the app's existing Warcraft Logs access are listed. Private or unlisted logs that this access cannot see are not found.
- **Raid-level summary only.** Entries show report-level facts (zone, time, difficulty, kills). Per-character performance such as parses on the welcome page is out of scope. The todo's "Rework Raids page" item covers that.
- **Same investigation as today.** Clicking a raid reuses the existing one-click investigation and its server-owned kickoff wording. This feature adds no new analysis behaviour.
- **Stored raids are kept.** Stored recent raids are not deleted on a schedule. Only the most recent ones are shown.
- **Background fetches use the background lane.** They share the app's overall Warcraft Logs access, concurrency cap and rate limits, but are confined to the background lane (FR-020, FR-024), so they cannot starve chat tool calls.
- **The side mission can ship in phases.** The async client and lanes come first. Tools then move over one at a time, and the old thread pools are removed last. Each phase must leave the app working, and the welcome page's new calls use the async client from the start. Exact lane sizes are a planning decision.
- **Out of scope for the side mission:** the two-way WebSocket with a user cancel button (PERF-202), model-stream timeouts (PERF-203), general coordination across multiple server instances (PERF-210), beyond the refresh lock in FR-025 (Warcraft Logs caches and lanes stay per instance) and the other findings in the QA report. FR-019's cancellation applies whenever the server cancels a turn, but this feature adds no new way for the user to cancel.
