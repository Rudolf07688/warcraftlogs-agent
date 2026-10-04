# Feature Specification: Captured-Metadata Reuse, Findings-Based Reports & Role-Aware Profiles

**Feature Branch**: `007-metadata-reports-profiles`

**Created**: 2026-10-03

**Status**: Draft

**Input**: User description (todo.txt Phase 5): "1. Capture metadata details such as 'Known Raids', 'known players' etc. dynamically as tool calls are successful. This must be used as a sort of 'cache' and help speed up follow-up other conversations app-wide. 2. Improve PDF report downloads: it shouldn't just be a copy of the conversation text; it needs to extract information from the chat and generate a full report on what findings were discovered, not what was said; the per-message report focussing doing the same, but only for the contents of that specific message. 3. Improve profile setup: more than one friend; roles for those characters (DPS/Tank/Healer)."

## Context

This phase builds directly on what Phases 4–6 already shipped. Phase 4 (005) already: captures "known raids" from successful tool calls into a durable per-tenant store, injects a profile-based "known player" preamble into the agent each turn, caches Warcraft Logs API results in-process, and exports conversation-level **and** per-message PDFs (markdown → rendered, with charts attached). Phase 6 (006) added multi-tenancy, so every user is an isolated tenant and "app-wide" means **per-tenant, across that user's conversations** — never shared between users.

Phase 5 is therefore a set of **refinements to existing capabilities**, not greenfield features. Three things are genuinely new:

1. **Captured metadata is never surfaced back to the agent.** Raids are captured but the agent's context preamble is built from the manually-entered profile only; captured raids/players/zones are not reused across conversations. This phase closes that loop and broadens what is captured.
2. **PDF reports are formatters, not analysts.** The export renders the conversation transcript (with charts); it does not synthesize *what was discovered*. This phase makes the report an analytic findings document, for both the whole conversation and a single message.
3. **Characters have no raid role.** A character's relationship (self/friend) exists, but there is no Tank/Healer/DPS attribute. This phase adds an optional raid role per character and feeds it into agent context. (Multiple friends already work; this phase verifies and polishes that.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Captured metadata reused across a user's conversations (Priority: P1)

As the user explores their raids, players, and zones over many separate conversations, the assistant remembers what it has already seen for that user and reuses it — so a brand-new conversation already "knows" the user's known raids, the players they've looked up, and the zones/bosses they've investigated, without re-asking or re-querying Warcraft Logs. This metadata is captured automatically and silently whenever a tool call succeeds, and it is private to that user.

**Why this priority**: The capture pipeline and the context-injection mechanism both already exist; the missing wire-up — surfacing captured metadata into the agent's context across conversations — delivers the headline value ("speed up follow-up conversations app-wide") at low cost and low risk. It is the backbone refinement of this phase.

**Independent Test**: In one conversation, ask about a Warcraft Logs report so its raid is captured; open a brand-new conversation (same user) and reference that raid loosely ("that pull from earlier", or by its guild/zone/date); confirm the assistant resolves it and answers without re-issuing the report-metadata lookup, and that a different user sees none of it.

**Acceptance Scenarios**:

1. **Given** a user with no captured metadata, **When** a turn runs, **Then** the assistant's behavior and injected context are unchanged from today (no regression on an empty store).
2. **Given** a successful report-scoped tool call in conversation A, **When** the user opens conversation B (same account) and asks about that raid by guild/zone/date, **Then** the assistant's context already includes that known raid and it answers without a fresh report-metadata lookup.
3. **Given** a successful character lookup naming a player not in the user's profile, **When** a later conversation references that player loosely, **Then** the player is present in the user's known-players metadata and the assistant can disambiguate name → server/region without re-asking.
4. **Given** a successfully resolved boss/zone, **When** a follow-up names that boss ambiguously, **Then** the known-zone/encounter metadata lets the assistant pick the correct encounter/zone without re-resolving it.
5. **Given** user X has captured metadata, **When** user Y runs any turn, **Then** none of X's known raids/players/zones ever appear in Y's context or storage (strict per-tenant isolation).
6. **Given** a user who has accumulated a large history, **When** the context is assembled for a turn, **Then** only the most recently relevant captured entries are included and the injected block stays within a bounded size.
7. **Given** a metadata capture write fails or the metadata is unavailable, **When** the turn proceeds, **Then** the turn still completes normally (capture is best-effort and never blocks or fails a turn).

---

### User Story 2 - Conversation-level findings report (Priority: P1)

When the user downloads a report for a whole conversation, they get an analytic document describing **what was discovered** — a summary of what was investigated, the key metrics found, results grouped by boss/encounter and/or player, and recommendations — rather than a transcript of the back-and-forth. The charts and graphs the conversation produced are still included.

**Why this priority**: This is the headline ask for the reporting part of the phase — a report of findings, not a copy of the chat — and it is the default download users already reach for. The rendering, chart embedding, and endpoint all exist; only the body content changes, so it is high-value and well-scoped.

**Independent Test**: Open a multi-turn analysis conversation (parses/rankings/boss results discussed), download the conversation report, and confirm the body is a structured findings synthesis organized by topic (not by chat turn), with the same charts still attached.

**Acceptance Scenarios**:

1. **Given** a conversation where the assistant analyzed several boss pulls, **When** the user downloads the report, **Then** the document presents findings organized by topic/encounter, describing what was discovered rather than reproducing the dialogue.
2. **Given** the analysis mentioned specific parse percentiles or performance numbers, **When** the report is generated, **Then** those key metrics appear in a "Key Findings" section.
3. **Given** multiple bosses were discussed, **When** the report is generated, **Then** results are grouped per boss/encounter.
4. **Given** the assistant made recommendations, **When** the report is generated, **Then** a recommendations/conclusions section captures them.
5. **Given** the conversation captured graphs and chart artifacts, **When** the report is generated, **Then** those charts still appear in the document.
6. **Given** the conversation is only greetings/setup with no analysis, **When** the report is generated, **Then** it honestly states there were no substantive findings rather than fabricating them (and still renders any attached charts, or notes there are none).
7. **Given** the findings synthesis cannot complete (model error or timeout), **When** the user downloads, **Then** the request fails cleanly with a clear error and no partial or misleading file is returned.

---

### User Story 3 - Per-message findings report (Priority: P2)

Each substantial assistant reply carries its own "Download report" control that produces the same analytic findings document, but scoped to just that one reply — synthesizing what that answer discovered, using its originating question for context, and including only that reply's charts. Other messages are excluded.

**Why this priority**: It delivers the same findings value at per-answer granularity, which is the most shareable unit, but it depends on the conversation-level synthesis pipeline (US2) and reuses the existing per-message scoping, so it ships second.

**Independent Test**: Click the per-reply "Download report" control on one assistant answer; confirm the document synthesizes only that reply's findings (plus its originating question for context) and includes only that reply's charts, excluding other messages.

**Acceptance Scenarios**:

1. **Given** one assistant reply with findings, **When** the user downloads its message report, **Then** the document synthesizes findings from that reply's content only.
2. **Given** other replies exist in the conversation, **When** the user downloads one reply's report, **Then** none of the other replies' findings appear.
3. **Given** the reply had charts/graphs bound to it, **When** the report is generated, **Then** only those charts appear.
4. **Given** the originating user question, **When** the report is generated, **Then** it is used as context for the synthesis, but the output is findings-shaped, not a transcript.
5. **Given** the reply is short/acknowledgement/chit-chat with no findings, **When** the user downloads, **Then** the report clearly states there are no substantive findings rather than inventing them.
6. **Given** the synthesis cannot complete for that reply, **When** the user downloads, **Then** the request fails cleanly with no partial or misleading file.
7. **Given** both the conversation-level and per-message reports, **When** either is generated, **Then** output structure and quality are consistent because both flow through one shared synthesis-and-render pipeline.

---

### User Story 4 - Role-aware profile with multiple friends and raid roles (Priority: P2)

The user can record multiple friend characters (not just one) and each character — their own and each friend's — carries a raid role of Tank, Healer, or DPS. The system defaults each character's role from its Warcraft-Logs-resolved specialization (e.g. a Protection spec defaults to Tank), and the user can override that default or set a role for a character whose spec has not resolved. The assistant uses these roles as standing context so its answers are role-aware (a tank's parse is judged differently from a DPS's).

**Why this priority**: Multiple friends already function, so the net-new user value is the raid role; it meaningfully improves answer quality, but the app is fully usable without it, so it ranks P2.

**Independent Test**: Save a self character and at least two friends whose specs resolve to different roles, confirm each shows an auto-inferred role; override one to a different role, reload the profile and confirm the override persists over the inferred default; then ask a role-sensitive question and confirm the assistant's context reflects each character's effective role.

**Acceptance Scenarios**:

1. **Given** the profile panel is open, **When** the user adds friends, **Then** they can add more than one friend with no cap, and each friend persists.
2. **Given** a character whose specialization resolves to a tanking/healing/damage spec, **When** no role override is set, **Then** the character's effective raid role is defaulted from that spec (e.g. a Protection spec → Tank).
3. **Given** the user sets or changes a character's raid role to Tank, Healer, or DPS, **When** they save it, **Then** that user-set role overrides any spec-inferred default.
4. **Given** a character's role was user-overridden, **When** the user reloads the profile, **Then** the override persists and is displayed next to that character (not reverted to the inferred default).
5. **Given** a character whose spec has not resolved and whose role the user has not set, **When** the profile renders, **Then** the character is still valid and shown cleanly without a role (effective role is simply unset).
6. **Given** a character has an effective raid role (inferred or overridden), **When** the user asks a question about that character, **Then** the assistant's standing context includes that role (e.g. "Thrall — Tank") and answers can be role-aware; **when** the effective role is unset, the context is unchanged from today (no empty-role artifacts).
7. **Given** the user adds a friend who is already saved (same name/server/region), **When** they submit, **Then** it is rejected with a clear "already added" message rather than a generic failure.

---

### Edge Cases

**Captured metadata (US1)**

- A player/character name that collides across servers/regions must be stored with its qualifying identity (name + server + region), not by name alone.
- A captured report whose zone or guild is unknown must still be recorded gracefully (missing fields tolerated).
- Metadata captured from a source that later becomes stale or inaccessible (e.g. a deleted report) should remain harmless rather than break a turn; freshness/invalidation is best-effort.
- A user with a very large history (hundreds of raids/players) must not overflow the agent's context budget — the injected block is recency/relevance-capped.
- A player discovered via tools who is also added to the profile must not be double-listed (profile characters and discovered players are reconciled).
- An encounter resolution that returns only a name with no stable encounter identifier is not persisted as a known encounter (deduplication requires a stable id); such name-only matches are simply not cached, by design, rather than stored ambiguously.
- Capture must behave correctly around the mid-turn commit/re-scope handling so it never crosses tenants.

**Findings reports (US2, US3)**

- A conversation or message that is pure chit-chat/greeting/error must produce a report that honestly states there were no substantive findings, not a fabricated one.
- Very long conversations may exceed the synthesis input limit and must be handled gracefully (truncation/degradation) rather than failing opaquely.
- Findings corrected across turns (a number later revised) should be consolidated to the latest value, not duplicated.
- A reply with charts but trivial narrative must still attach its charts even if the findings section is thin.
- Synthesis latency on a synchronous download must be bounded by a timeout with a clear failure, never a hung request.

**Role-aware profile (US4)**

- An effective role that is unset (spec unresolved and no user override) must leave the character fully functional and omit the role cleanly from both UI and agent context.
- A user-set role that conflicts with the character's Warcraft-Logs-resolved spec (e.g. user overrides to Healer when the resolved spec maps to DPS) is accepted with the user override authoritative for display/context; no discrepancy warning in this version.
- A spec that maps ambiguously or to no clear role must leave the inferred default unset (not guessed), so the character simply shows no role until the user sets one.
- When a character's spec later re-resolves, the inferred default may change, but any existing user override must be preserved.
- Flex/dual-role specs are represented by a single effective role; multi-role is out of scope for this version.
- Existing character rows created before this feature must remain valid with no override and an inferred-or-unset effective role (no backfill required, no breakage).
- The character's raid role is a distinct attribute from the existing self/friend relationship; the two must never be conflated.

## Requirements *(mandatory)*

### Functional Requirements

**Captured-metadata reuse (US1)**

- **FR-001**: On a successful tool call, the system MUST persist captured metadata to a durable, per-tenant store that survives process restart (distinct from the ephemeral in-process Warcraft Logs result cache).
- **FR-002**: The system MUST continue to capture "known raids" as it does today, extending rather than replacing the existing tracked-raid store.
- **FR-003**: The system MUST capture "known players"/characters discovered from successful character lookups and report actor data, deduplicated and identified unambiguously (name + server + region), distinct from manually-entered profile characters.
- **FR-004**: The system MUST capture "known zones"/encounters the user has queried or resolved, deduplicated by identity.
- **FR-005**: The system MUST surface the user's captured metadata into the assistant's per-turn standing context across **all** of that user's conversations, extending the existing context preamble rather than adding a second, parallel injection path.
- **FR-006**: All metadata capture, storage, and injection MUST be scoped to a single tenant; no captured entity may ever appear in another tenant's context or storage.
- **FR-007**: The injected metadata block MUST be bounded (recency/relevance-capped) so the assistant's context stays within budget regardless of how much history a user accumulates.
- **FR-008**: Metadata capture MUST be best-effort: a capture failure MUST NOT fail, block, or visibly disrupt the turn.
- **FR-009**: Captured metadata MUST reduce redundant Warcraft Logs calls on follow-ups by letting the assistant answer from known context instead of re-querying. Specifically, a repeat reference to an **already-known raid MUST NOT trigger a new report-metadata lookup** (zero additional such calls), and MUST NOT increase the total Warcraft Logs lookups versus the cold path.
- **FR-010**: Metadata capture MUST remain a server-side fan-out off the existing tool-success hub and MUST NOT require changes to individual tools.
- **FR-011**: With no captured metadata, all existing behavior MUST remain unchanged (the feature is strictly additive).

**Findings-based reports (US2, US3)**

- **FR-012**: The system MUST generate a report body by synthesizing the in-scope conversation content into findings (what was discovered), not by reproducing the message transcript.
- **FR-013**: A findings report MUST include, where the content supports it: a summary of what was investigated, the key findings/metrics discovered, results grouped per boss/encounter and/or per player, and recommendations/conclusions.
- **FR-014**: A findings report MUST still embed the charts/graphs and chart artifacts that the current export attaches, scoped identically to today (all for a conversation report; only the matching reply's charts for a per-message report).
- **FR-015**: The system MUST offer a conversation-level findings report and a per-message findings report; the per-message report MUST synthesize only that reply's content plus its originating user question for context, and MUST exclude all other messages.
- **FR-016**: Conversation-level and per-message reports MUST share a single synthesis-and-render pipeline, differing only in the scoped input, so output structure and quality are consistent.
- **FR-017**: When the in-scope content contains no substantive findings, the report MUST clearly indicate the absence of findings rather than inventing them.
- **FR-018**: On synthesis failure, timeout, or empty output, the report request MUST fail with a clear error and MUST NOT return a partial or misleading file.
- **FR-019**: The synthesis step MUST run off the request event loop so it does not block the server, and MUST be bounded by a timeout.
- **FR-020**: The existing report header/title behavior MUST be preserved (tracked-raid label preference for conversation reports; conversation-title fallback).
- **FR-021**: The existing report controls and download entry points (conversation-level and per-message) MUST continue to work unchanged from the user's perspective (no new user steps required).

**Role-aware profile (US4)**

- **FR-022**: The system MUST support an effectively unlimited number of friend characters per user; no numeric cap may be introduced.
- **FR-023**: A duplicate friend (same name/server/region) MUST be rejected, and the UI MUST surface a clear "already added" message rather than a generic failure.
- **FR-024**: Each character (self and every friend) MUST have a raid-role attribute (an effective role), distinct from the existing self/friend relationship attribute.
- **FR-025**: The system MUST default a character's raid role by inferring it from the character's Warcraft-Logs-resolved specialization (mapping each spec to Tank, Healer, or DPS); when the spec has not resolved, the inferred default is simply unset.
- **FR-026**: A user-set raid role MUST override any spec-inferred default, and the override MUST persist across profile reloads and across subsequent spec re-resolutions (it is not reverted to the inferred value).
- **FR-027**: The allowed user-set raid-role values MUST be exactly Tank, Healer, and DPS, plus an unset/none state (which clears the override and returns the character to its inferred default); any other value MUST be rejected with a validation error, leaving the character unchanged.
- **FR-028**: Setting or updating a character's raid role MUST be an in-place edit (self remains a single entry; a friend's role change MUST NOT create a duplicate character).
- **FR-029**: The profile read path and the UI MUST return and display each character's effective raid role (inferred or overridden) where one exists, and MUST indicate when a role is user-set versus inferred.
- **FR-030**: When a character has an effective raid role, it MUST be included in the assistant's standing context for that character so answers can be role-aware; when the effective role is unset, the context MUST be identical to today's (no empty-role artifacts).
- **FR-031**: Introducing the raid role MUST NOT change character identity/uniqueness rules, and existing characters created before this feature MUST remain valid with no role override and an inferred-or-unset effective role (no backfill, no breakage).

### Key Entities *(include if feature involves data)*

- **Known Raid**: A Warcraft Logs report the user has pulled data for (already exists today): report identity, label, zone, guild, date, and its distinct boss list. Extended, not replaced.
- **Known Player**: A character the user has looked up via tools, identified by name + server + region (optionally class/spec), distinct from profile-entered characters.
- **Known Zone/Encounter**: A raid zone or boss the user has queried or resolved, identified by its zone/encounter identity and name.
- **Known Guild**: A guild surfaced from captured reports, distinct from the single profile main guild.
- **Per-tenant Metadata Store**: The durable, restart-surviving, per-user collection of the above — the authoritative source feeding the assistant's standing-context preamble across conversations.
- **Findings Report**: The synthesized analytic document (summary of what was investigated, key findings/metrics, per-boss/per-player results, recommendations) that replaces the transcript body; produced for either a whole conversation or a single reply, with charts attached.
- **Report Scope**: The discriminator (whole conversation vs. a single reply) that selects the synthesis input while feeding one shared pipeline.
- **User Character**: A self or friend character in the user's profile, carrying the existing relationship attribute (self vs. friend), identity (name/server/region), resolved class/spec and guide, and a **raid role** — an effective Tank/Healer/DPS/unset value derived from a spec-inferred default plus an optional user override that takes precedence.
- **Standing-context Preamble**: The per-turn, non-persisted text block injected into the assistant, extended by this feature to include captured metadata (US1) and character raid roles (US4).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A raid, player, or zone captured in one conversation is present in the assistant's context in a subsequent conversation for the same user 100% of the time, and never appears for any other user (zero cross-tenant leakage).
- **SC-002**: A follow-up that references an already-known raid issues **zero** report-metadata lookups (a deterministic 0, versus ≥1 in the equivalent cold conversation), and completes with no more Warcraft Logs lookups than the cold path overall.
- **SC-003**: The injected captured-metadata context block stays within a fixed size budget regardless of how much history a user accumulates, and with no captured metadata the turn behaves identically to today.
- **SC-004**: A reader who never saw the chat can learn the key discoveries (which bosses/players, the headline metrics, the recommendation) from a conversation report alone; the report body is organized by findings/topic, not by chat turns.
- **SC-005**: A per-message report contains exactly the target reply's findings plus its originating question for context, includes only that reply's charts, and excludes all other messages, in 100% of exports.
- **SC-006**: A chit-chat-only conversation or message produces a report that honestly states there were no substantive findings, and a synthesis failure returns a clear error with no partial file, in 100% of such cases.
- **SC-007**: A user can save a self character plus at least three friends; each character shows an effective raid role that is correctly inferred from its resolved spec, a user override persists over that inferred default across reloads and re-resolutions, and characters with an effective role show it in the assistant's context while characters with an unset role leave the context byte-identical to today.
- **SC-008**: Every existing capability continues to work unchanged when the new metadata store is empty and no raid roles are set or inferred (additive, zero regressions).

## Assumptions

- **Per-tenant "app-wide"**: With multi-tenancy (006) in place, "app-wide" means across all of a single user's conversations, never shared between users. Captured metadata is stored and injected under the existing per-tenant isolation.
- **Capture reuses the existing hub**: New metadata captures plug into the existing tool-success fan-out alongside the current raid/graph/artifact captures, following the same best-effort, per-tool-agnostic pattern; no new external data calls are added where existing tool outputs already contain the data.
- **Context injection extends the existing preamble**: Captured metadata and raid roles are added to the single existing standing-context preamble rather than via a new injection path, reusing its existing size caps and empty-state conventions (Constitution Principle I, DRY).
- **Metadata store complements, not replaces, the result cache**: The durable per-tenant metadata store is a distinct layer from the ephemeral in-process Warcraft Logs result cache; the result cache is left as-is.
- **Findings synthesis via an LLM pass**: The report body is produced by an LLM summarizing the in-scope chat content, reusing the established off-event-loop, fail-closed backend LLM pattern already used for background generation; the existing markdown → PDF renderer and chart embedding are reused unchanged. The synthesis output is markdown compatible with the current renderer.
- **Synthesis runs per download (no caching) for this version**: To stay simple (Constitution Principle III, YAGNI), each download re-runs synthesis; persisting/caching synthesized reports with invalidation is deferred and may be added later behind the same interface if cost/latency warrant it.
- **Synthesis uses the chat as its source (no web search)**: Findings come from the conversation content itself, so a plain (non-web-search) model call is assumed; it is independent of the user's selected chat model.
- **Reports reuse existing scoping and endpoints**: Per-message vs. conversation scoping reuses the existing message-sequence binding and the existing two download endpoints/controls; the frontend requires no change to how reports are requested.
- **Raid role is spec-inferred with user override**: Each character's raid role defaults from its Warcraft-Logs-resolved spec (via a spec → Tank/Healer/DPS mapping); the user may override the default, and the override is authoritative over the inferred value and persists across spec re-resolutions. When the spec has not resolved and no override is set, the effective role is simply unset. Dual-role/flex support and spec-vs-override discrepancy warnings are out of scope for this version.
- **Raid role is a new attribute, not the existing relationship field**: The existing self/friend "role" and the new Tank/Healer/DPS raid role are orthogonal and both live on the character; the new attribute is added additively (nullable, no backfill).
- **Multiple friends already work**: Adding more than one friend already functions end-to-end; this phase verifies that and polishes the related UX (duplicate messaging), rather than building it from scratch.
- **Builds on prior phases**: This feature assumes Phases 1–4 (streaming chat, raid sourcing, guild/profile context, caching, PDF export, artifacts) and Phase 6 (multi-tenancy) are in place and working.
- **Desktop-primary**: Desktop remains the primary target; narrow layouts stay usable, consistent with prior phases.
