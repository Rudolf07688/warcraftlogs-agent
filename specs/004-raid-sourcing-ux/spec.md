# Feature Specification: Raid Sourcing, Tracking & Report UX

**Feature Branch**: `004-raid-sourcing-ux`

**Created**: 2026-10-02

**Status**: Draft

**Input**: User description (todo.txt Phase 3): "1. Always paste links to the warcraftlogs url that you are sourcing information from (or just query parameters if easier). 2. Duplicating raids tracked in the side bar? 2.1 Display date and time of the raid encounter + boss name if applicable. 3. As specific bosses come up in the raid results, list them as checkboxes to send to the agent prompt to focus/filter on. 4. PDF report not working anymore. Previous render looked terrible. 5. When entering a new chat the backend must preemptively send a message to the agent, invisible to the user, saying 'Greetings, Barnaby!' so the agent greets you with a warm greeting when you start. The greeting prompt should be sent on application startup and cached for new chats during the session." — plus a re-scope to adopt the `react-modern-ui` high-fantasy polish patterns (see Clarifications).

## Clarifications

### Session 2026-10-02

- Q: How should the `react-modern-ui` fantasy-polish patterns be incorporated relative to feature 004? → A: Full adoption now — the visual overhaul is re-scoped as a headline, app-wide part of this feature (new User Story 6, P1).
- Q: SSE-over-POST (per the skill) vs the app's existing WebSocket frame protocol? → A: Keep the existing WebSocket (decision delegated to the implementer). The current frames already map to the skill's event taxonomy; a transport migration would be gratuitous rework (Simplicity-First). Render patterns are layered onto the existing WS frames; optional `tool_progress` frames may be added for determinate cast bars.
- Q: How far should the frontend stack footprint go? → A: Full skill stack — React 19 (upgrade from 18), Tailwind v4, shadcn/ui, motion, streamdown, use-stick-to-bottom, @tsparticles, react-icons/gi. Recorded as a significant complexity/dependency increase in the plan's Complexity Tracking.
- Q: How does the skill's multi-theme system relate to the Phase 2 background toggle? → A: Ship ONE fixed, curated theme — no user-facing theme or background switcher. The existing background images are retained as the fixed theme backdrop. This supersedes the Phase 2 user-facing background toggle.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cited Warcraft Logs source links (Priority: P1)

When the assistant answers using data pulled from Warcraft Logs, it includes a clickable link back to the exact Warcraft Logs page the data came from (the report, and where relevant the specific fight, player, and metric view), so the user can verify any claim at its source with one click.

**Why this priority**: Source attribution is the trust backbone of an analytics assistant. Without a link back, users must manually reconstruct which report and fight a number came from. It is independently valuable even if nothing else ships, and it directly addresses the first and most-requested Phase 3 item.

**Independent Test**: Ask any analytical question about a specific report and fight, and confirm the answer contains a working Warcraft Logs link that opens the correct report (and, where applicable, the correct fight / player / metric view) in a new tab.

**Acceptance Scenarios**:

1. **Given** the assistant answers using data from a specific report, **When** the response renders, **Then** it includes a clickable Warcraft Logs link to that report.
2. **Given** the answer concerns a specific fight (encounter/pull), **When** the link is produced, **Then** it points to that fight within the report (not just the report root).
3. **Given** the answer focuses on a specific player and metric (e.g. a damage parse), **When** the link is produced, **Then** it narrows to that player/metric view where the data supports it.
4. **Given** a link is shown, **When** the user clicks it, **Then** it opens the Warcraft Logs page in a new browser tab without navigating away from the chat.
5. **Given** an answer draws on multiple reports or fights, **When** it renders, **Then** each distinct source is linked rather than collapsed into a single ambiguous link.
6. **Given** the assistant answers from general knowledge or web search rather than a Warcraft Logs lookup, **When** it responds, **Then** it does not fabricate a Warcraft Logs link.

---

### User Story 2 - Accurate, de-duplicated raid list with date/time and boss (Priority: P1)

The sidebar list of previously-investigated raids shows each raid exactly once, labelled with the raid's own date and time and (where known) the boss/encounter, so the user can tell at a glance which raid night each entry refers to and reopen it reliably.

**Why this priority**: The raid list is the primary navigation for returning to prior analysis. Duplicate entries and a misleading timestamp (showing when it was last asked about rather than when the raid happened) make it untrustworthy. This is a visible defect on core navigation, so it ranks alongside source links as P1.

**Independent Test**: Investigate the same raid report across two separate turns/chats, confirm only one sidebar entry exists for it, and confirm the entry shows the raid's actual date/time (and boss name when known) rather than only the last-asked time.

**Acceptance Scenarios**:

1. **Given** a raid report has already been investigated, **When** it is referenced again in a later turn or a different chat, **Then** the sidebar still shows a single entry for that raid, not a duplicate.
2. **Given** two turns reference the same brand-new report at nearly the same time, **When** both complete, **Then** only one sidebar entry results (no duplicate from a race).
3. **Given** a raid entry is displayed, **When** the user views the sidebar, **Then** it shows the raid's own date and time of occurrence.
4. **Given** the boss/encounter for a raid is known, **When** the entry renders, **Then** the boss/encounter name is shown on the entry.
5. **Given** the boss/encounter is not known (e.g. a whole-report query), **When** the entry renders, **Then** it still renders cleanly with the raid date/time and no broken or empty boss field.
6. **Given** multiple raid entries exist, **When** the list is shown, **Then** entries remain sorted so the most relevant/recent raids are easy to find.

---

### User Story 3 - PDF report that renders correctly (Priority: P2)

The user can download a PDF of a conversation's analysis and it renders cleanly — tables are laid out as tables, lists and headings are formatted, long values don't overflow the page, and included graphs appear — so the PDF is genuinely shareable rather than a broken dump.

**Why this priority**: The PDF export is an existing, user-facing feature that is currently broken/ugly (notably markdown tables rendering as raw pipe text). It is high-value for sharing findings but ranks below the always-on trust and navigation fixes.

**Independent Test**: Produce an analysis that includes a markdown table, headings, bullet points, and at least one graph, download the PDF, and confirm every element renders legibly with no raw markup, no overflow off the page, and graphs present.

**Acceptance Scenarios**:

1. **Given** an analysis containing a markdown table, **When** the PDF is generated, **Then** the table renders as an aligned table, not raw `| col | col |` text.
2. **Given** an analysis containing headings, bulleted lists, and numbered lists, **When** the PDF is generated, **Then** each is formatted as its intended structure.
3. **Given** content with long unbroken tokens (report codes, URLs, long ability names), **When** the PDF is generated, **Then** the text wraps within the page margins without overflowing or being clipped.
4. **Given** a conversation with captured graphs, **When** the PDF is generated, **Then** the graphs appear in the PDF.
5. **Given** the user requests a PDF, **When** generation succeeds, **Then** the file downloads and opens in a standard PDF viewer without errors.
6. **Given** generation cannot complete for a conversation, **When** the user requests it, **Then** they receive a clear failure message rather than a silently corrupt or empty file.

---

### User Story 4 - Boss focus checkboxes from raid results (Priority: P2)

As the assistant surfaces the specific bosses/encounters present in a raid, the user is shown those bosses as selectable checkboxes; selecting one or more and sending folds the chosen bosses into the next prompt so the agent focuses its analysis on exactly those encounters.

**Why this priority**: This is a convenience/steering feature that reduces typing and sharpens multi-boss analysis. It depends on encounter data being surfaced to the UI and is valuable but not a defect fix, so it ranks P2.

**Independent Test**: Run a query that returns a raid's fight list, confirm the encountered bosses appear as checkboxes, select two, send, and verify the next prompt to the agent is scoped to those two bosses and the answer reflects that focus.

**Acceptance Scenarios**:

1. **Given** a response that surfaced a raid's encounter list, **When** it renders, **Then** the distinct bosses/encounters are offered as selectable checkboxes.
2. **Given** boss checkboxes are shown, **When** the user selects one or more and sends, **Then** the chosen bosses are included in the next prompt so the agent focuses on them.
3. **Given** the user selects no boss, **When** they send a normal message, **Then** behavior is unchanged (no forced filter).
4. **Given** a raid had many encounters, **When** the checkboxes render, **Then** they remain readable and usable (no overflow of the message area) on both wide and narrow widths.
5. **Given** the user selected bosses on a prior turn, **When** a new turn begins, **Then** stale selections are not silently reapplied without the user's intent.

---

### User Story 5 - Warm Barnaby greeting on a new chat (Priority: P3)

When the user starts a new chat, Barnaby greets them warmly right away, without the user having to type anything first, and the greeting appears promptly rather than after a long wait.

**Why this priority**: A welcoming first impression that reinforces the Barnaby persona, but purely additive polish with no analytical impact, so it ranks last.

**Independent Test**: Start a new chat and, without typing, confirm a warm Barnaby greeting appears promptly; start several new chats in the same session and confirm the greeting appears quickly each time.

**Acceptance Scenarios**:

1. **Given** the user starts a new chat, **When** the empty chat opens, **Then** a warm Barnaby greeting appears without the user sending a message.
2. **Given** the greeting is generated from a hidden kickoff ("Greetings, Barnaby!"), **When** the chat renders, **Then** that kickoff prompt is not shown to the user — only Barnaby's greeting.
3. **Given** the user starts additional new chats within the same session, **When** each opens, **Then** the greeting appears promptly (served from a session cache rather than waiting on a fresh model call each time).
4. **Given** the user then asks a real question, **When** they send it, **Then** the conversation proceeds normally with the greeting as the opening turn.
5. **Given** a greeting cannot be produced, **When** a new chat opens, **Then** the chat still opens cleanly (a graceful fallback or no greeting) rather than blocking the user.

---

### User Story 6 - High-fantasy UX polish (Priority: P1)

The entire chat experience is restyled into one cohesive, original "warcraft-like" (IP-safe) high-fantasy look: a single curated theme built on CSS design tokens, smoothly "inscribed" streaming text, tool calls presented as animated "spellcasting" cards (summoning → casting → resolved/fizzled), and subtle ambient effects — while staying readable, performant, and respectful of reduced-motion preferences.

**Why this priority**: The user re-scoped this feature so the visual overhaul is a headline outcome (full adoption). It elevates every other slice (source links, raid list, boss checkboxes, greeting) by giving the whole app a premium, consistent feel, and it is applied app-wide rather than only to this feature's new UI.

**Independent Test**: Load the app and confirm one cohesive fantasy theme, smooth (non-jittery) streaming text that renders still-incomplete markdown safely, tool calls shown as themed spell cards with cast progress and resolve/fizzle states, and that enabling reduced-motion disables animation while the UI stays fully usable at a smooth frame rate.

**Acceptance Scenarios**:

1. **Given** the app loads, **When** it renders, **Then** a single curated fantasy theme (color/font/glow/texture tokens) is applied app-wide, with **no** user-facing theme or background switcher.
2. **Given** the agent is streaming an answer, **When** tokens arrive in uneven bursts, **Then** text appears smoothly via an adaptive buffer, renders incomplete markdown safely (no flashing `**` or broken tables), and shows a streaming caret with smooth height growth.
3. **Given** the agent starts a tool call, **When** the card appears, **Then** it is a themed spell card (per-tool icon/color/verb/flavor; unknown tools fall back to a default) and is held a minimum (~600 ms) so it never flickers.
4. **Given** a tool call finishes, **When** it succeeds, **Then** the card resolves (burst) and collapses to a compact chip showing a short human-readable summary and duration; **when** it fails, **Then** the card fizzles with a clear reason.
5. **Given** several tool calls run in parallel, **When** they render, **Then** their cards stack/stagger and each resolves independently.
6. **Given** the user prefers reduced motion, **When** the UI renders, **Then** blur/rotation/particles are disabled (simple fades/static kept) and the experience stays fully usable and smooth.
7. **Given** the existing background images, **When** the theme is applied, **Then** they are retained as the fixed theme backdrop and chat text stays legible over them.
8. **Given** CC-licensed assets (e.g. game-icons.net) are used, **When** the app ships, **Then** the required CC BY 3.0 attribution is present and no third-party game (Blizzard) logos/UI art/commercial fonts are used.

---

### Edge Cases

- Tool calls that return from cache (near-instant) must still honor the minimum cast-card display time so cards never flicker.
- A tool name with no spell-registry entry must fall back to a default spell presentation rather than rendering nothing or crashing.
- Streaming must never show broken/partial markdown artifacts (e.g. dangling `**`, half-rendered tables) even when a token boundary splits markup.
- Reduced-motion and background-image legibility must both hold for every other story's new UI (source links, raid entries, boss checkboxes, greeting), not just the base chat.
- A Warcraft Logs link must be well-formed even when only partial context is known (report only, vs report+fight, vs report+fight+player+metric); it should narrow as far as the available data allows and no further.
- The visible raid date/time should reflect the raid's own occurrence; if the underlying source only provides a date (no precise time), the entry should degrade gracefully to showing the date.
- When the same report is referenced concurrently from two tabs/sockets for the first time, the system must still end with a single sidebar entry.
- PDF generation must not hang indefinitely on very large conversations; it should complete or fail clearly within a reasonable time.
- Boss checkboxes must de-duplicate repeated encounters (e.g. multiple pulls of the same boss) into one selectable boss.
- A boss-focused prompt must still be answerable if the selected boss has no data in the report (clear "no data for X" rather than a silent empty answer).
- The cached greeting must not leak between unrelated users/sessions and must refresh appropriately across application restarts.
- If the greeting is still being prepared when the user starts typing, their input must take priority and not be clobbered by a late-arriving greeting.

## Requirements *(mandatory)*

### Functional Requirements

**Source links (US1)**

- **FR-001**: When an answer uses data retrieved from Warcraft Logs, the assistant MUST include a clickable link to the corresponding Warcraft Logs page.
- **FR-002**: Source links MUST narrow to the specific fight, player, and metric view when the answer is about that specific scope and the data supports it; otherwise they link at the most specific available level (down to the report).
- **FR-003**: Links MUST open in a new browser tab and preserve the current chat state.
- **FR-004**: When an answer draws on multiple distinct sources, each distinct source MUST be individually linked.
- **FR-005**: The assistant MUST NOT fabricate Warcraft Logs links for content not sourced from a Warcraft Logs lookup.

**Raid list (US2)**

- **FR-006**: The sidebar MUST show each investigated raid report exactly once (no duplicates), including across different chats and repeated references.
- **FR-007**: Concurrent first-time references to the same report MUST resolve to a single raid entry (no duplicate from a race).
- **FR-008**: Each raid entry MUST display the raid's own date and time of occurrence, and MUST degrade to date-only when time is unavailable.
- **FR-009**: Each raid entry MUST display the boss/encounter name when known, and render cleanly when it is not.
- **FR-010**: The raid list MUST remain sorted so the most recent/relevant raids are easy to locate.

**PDF report (US3)**

- **FR-011**: The PDF export MUST render markdown tables as laid-out tables.
- **FR-012**: The PDF export MUST render headings, bulleted lists, and numbered lists as their intended structures.
- **FR-013**: The PDF export MUST wrap long unbroken tokens within page margins without overflow or clipping.
- **FR-014**: The PDF export MUST include captured graphs when present.
- **FR-015**: On success the PDF MUST download as a valid file openable in standard viewers; on failure the user MUST receive a clear error rather than a corrupt/empty file.

**Boss focus (US4)**

- **FR-016**: When a response surfaces a raid's encounter list, the distinct bosses/encounters MUST be presented to the user as selectable checkboxes.
- **FR-017**: Selected bosses MUST be folded into the next prompt so the agent focuses analysis on those encounters.
- **FR-018**: With no boss selected, sending a message MUST behave exactly as it does today (no forced filtering).
- **FR-019**: Repeated pulls of the same boss MUST collapse to a single selectable boss, and the checkbox group MUST stay readable on narrow and wide widths.
- **FR-020**: Boss selections MUST NOT silently persist and reapply across unrelated new turns without user intent.

**New-chat greeting (US5)**

- **FR-021**: Starting a new chat MUST produce a warm Barnaby greeting without the user sending a visible message.
- **FR-022**: The hidden kickoff prompt ("Greetings, Barnaby!") MUST NOT be displayed to the user; only Barnaby's greeting is shown.
- **FR-023**: The greeting MUST be prepared at application startup and cached for reuse so subsequent new chats in the session render it promptly.
- **FR-024**: If a greeting cannot be produced, the new chat MUST still open cleanly with a graceful fallback (or no greeting) and never block the user.
- **FR-025**: After the greeting, a user's real first question MUST proceed as a normal conversation turn.

**Fantasy UX polish (US6)**

- **FR-026**: The UI MUST apply a single, curated high-fantasy theme defined via CSS design tokens (color, font, glow, texture), applied app-wide.
- **FR-027**: The UI MUST NOT expose a user-facing theme switcher or background toggle; the theme and backdrop are fixed by the product (this supersedes the Phase 2 user-facing background toggle).
- **FR-028**: The existing background images MUST be retained as the fixed theme backdrop, with chat-text legibility preserved over them.
- **FR-029**: Streamed answer text MUST render smoothly via an adaptive buffer (no token-burst jitter), MUST render incomplete/streaming markdown safely (no broken or flashing syntax), and MUST show a streaming caret with smooth height growth.
- **FR-030**: Chat auto-scroll MUST follow streaming output and stop fighting the user when they scroll up, offering a "back to bottom" affordance.
- **FR-031**: Each tool call MUST be presented as a themed "spell" card with a distinct icon/color/verb/flavor per tool (unknown tools fall back to a default), progressing through summoning → casting → resolved/fizzled states.
- **FR-032**: Tool cards MUST show cast progress (indeterminate, upgrading to determinate when progress data is available), remain visible for a minimum (~600 ms), resolve to a compact chip with a short human-readable summary and duration, and clearly surface failures with a reason.
- **FR-033**: Parallel tool calls MUST render as independently-resolving, stacked/staggered cards.
- **FR-034**: The UI MUST honor reduced-motion (disable blur/rotation/particles; keep simple fades/static) and sustain a smooth frame rate (~60 fps) during streaming.
- **FR-035**: Any CC-licensed assets (e.g. game-icons.net) MUST carry the required attribution (CC BY 3.0), and no third-party game (Blizzard) logos, UI art, or commercial fonts may be used.
- **FR-036**: The polish MUST apply consistently across all of this feature's new UI (source links, raid list entries, boss checkboxes, greeting) as well as the base chat.

### Key Entities *(include if feature involves data)*

- **Tracked Raid**: A previously-investigated Warcraft Logs report. Attributes relevant here: a unique report identity (for de-duplication), the raid's occurrence date/time, zone/guild context, associated boss/encounter(s) when known, and timestamps for sorting. Relates to the conversation(s) that investigated it.
- **Encounter / Boss**: A specific fight within a raid report (name/identifier, difficulty, kill-or-wipe). Surfaced to the UI as selectable focus items and optionally associated to a Tracked Raid for display.
- **Source Reference**: The report/fight/player/metric coordinates behind a cited answer, expressed to the user as a Warcraft Logs link.
- **Session Greeting**: A cached, pre-generated warm greeting reused for new chats within an application session.
- **Theme Tokens**: The fixed set of CSS design tokens (color, font, glow, texture) that define the single app-wide fantasy theme (no user-selectable variants).
- **Spell**: Per-tool presentation metadata (icon, color/hue, verb, rotating flavor lines) mapping each real tool name to its spellcasting visuals; unknown tools fall back to a default spell.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of answers that use Warcraft Logs data, at least one correct, clickable source link is present and resolves to the referenced report/fight.
- **SC-002**: The sidebar shows zero duplicate entries for the same report across repeated references and concurrent first-time references.
- **SC-003**: 100% of raid entries display the raid's own date (and time when available) and the boss name when known.
- **SC-004**: A PDF generated from an analysis containing a table, headings, lists, long tokens, and a graph renders all of them correctly, with zero instances of raw markup or off-page overflow.
- **SC-005**: Selecting bosses via checkboxes scopes the next answer to exactly those bosses in 100% of attempts, and selecting none leaves behavior unchanged.
- **SC-006**: A warm greeting appears on a new chat without user input, and on second and subsequent new chats within a session it appears in under ~1 second (served from cache).
- **SC-007**: The app presents exactly one cohesive fantasy theme with no user-facing theme/background switcher, and chat text remains legible over the retained background images.
- **SC-008**: Streaming text shows no visible token-burst jitter and never displays broken or flashing markdown while streaming.
- **SC-009**: 100% of tool calls render as spell cards that reach a resolved or fizzled state with a summary; parallel tool calls each resolve independently.
- **SC-010**: With reduced-motion enabled, all non-essential animation is disabled and the UI remains fully usable, and streaming sustains ~60 fps on a typical laptop.

## Assumptions

- Warcraft Logs links are the public web report URLs built from identifiers the tools already return (report code, fight id, player/source id, metric); no new external data source is required.
- "Raid date/time of occurrence" is derived from the report's own start time already captured during tracking; when only a date is available, date-only display is acceptable.
- De-duplication continues to key on the report's unique identity, and the existing persistence store is reused (no new datastore).
- Boss/encounter data is already produced by the existing fight-list lookup; this feature surfaces it to the UI rather than introducing new analysis.
- The PDF export continues to summarize the conversation's agent analysis and captured graphs; fixing rendering fidelity is the goal, not redesigning what content is included (though including user questions for context is acceptable if it improves readability).
- The greeting is a persona-consistent Barnaby message generated once per application session and cached in memory; it refreshes on application restart and is not persisted per user.
- This feature builds on the existing streaming chat, raid-tracking, and Barnaby persona delivered in prior phases; Phases 1 and 2 are complete.
- Mobile/narrow layouts should remain usable but desktop is the primary target, consistent with prior phases.
- **Visual overhaul (US6) is full-adoption and app-wide**: the `react-modern-ui` fantasy-polish patterns re-scope this feature as a headline and apply across the whole app, not only to this feature's new UI.
- **Frontend stack grows to the full skill stack**: React 19 (upgrade from React 18), Tailwind v4, shadcn/ui, motion, streamdown, use-stick-to-bottom, @tsparticles (+@tsparticles/slim), and react-icons/gi. This is a substantial complexity/dependency and tooling increase (incl. a React major upgrade) and is recorded/justified in the plan's Complexity Tracking per Constitution Principle III (Simplicity First).
- **Streaming stays on the existing WebSocket**: no migration to SSE-over-POST; the spellcasting/streaming UI is driven by the current WS frames (which already map to the skill's `tool_start`/`tool_end`/`token`/`done`/`error` taxonomy, with `meta` as run-start). Optional `tool_progress` frames may be added later for determinate cast bars.
- **Single fixed theme, no switcher**: one curated theme is shipped; the Phase 2 user-facing background toggle is removed. The existing background images are retained as the fixed theme backdrop.
- **IP-safe styling**: original "warcraft-like" look only; game-icons.net icons used under CC BY 3.0 with visible attribution; no Blizzard logos, UI art, or commercial fonts.
- **Reduced-motion and smooth frame rate (~60 fps) are hard acceptance constraints**, not nice-to-haves.
