# Feature Specification: Personalized Guild Context, Interactive Artifacts & Faster Analysis

**Feature Branch**: `005-guild-context-artifacts`

**Created**: 2026-10-02

**Status**: Draft

**Input**: User description (todo.txt Phase 4): "1. Define self/friend characters for extra context. Add guild name as well (limited to one main guild for current user); responses are more focussed to guild members (unless answering unrelated questions). 2. Store / cache results for quick access. 3. Speed up tool calls (parallelize tasks? Run predefined workflows? Subagents?). 4. Implement MCP communication protocol, specifically (but not limited to), being able to render plots and artifacts — perhaps use python plotly at the back and pass the json to the js plotly library so the graphs are nice and interactive. 5. The 'Download pdf report' button should sit on a specific message reply as well — taking only that message (with required context to generate the answer) and generate almost 'analytic' reports. 6. When you lock in the names in the 'Add a personal character' / 'Add guild name' / 'Add friend character', a background task should kick off that fetches and persists a guide to the characters' active spec for the agent to use in context. 7. Fix the rendering of agent responses such as LaTeX / mathematical equations."

## Clarifications

### Session 2026-10-02

- Q: How literal is the "MCP communication protocol" in item 4? → A: **Artifact rendering only.** Treat "MCP" as the *goal* of rendering rich in-chat artifacts. The backend emits structured artifact frames over the existing WebSocket and the frontend renders them interactively (Plotly figures from Python-produced JSON, plus tables/cards). No literal Model Context Protocol server/client is built; that would be gratuitous infrastructure (Constitution Principle III, Simplicity-First).
- Q: What identity scope should the self/friend/guild feature assume? → A: **Single global profile (static default tenant).** One "me" character, a list of friend characters, and one main guild, stored globally with no authentication. Multi-user accounts remain deferred to Phase X.
- Q: Where should the auto-fetched "guide to the character's active spec" (item 6) come from? → A: **Web search + Warcraft Logs.** A background task resolves the character's active spec from Warcraft Logs, then uses the existing web-search grounding capability to compile a concise rotation/stat/talent guide, persisted as agent context.
- Q: What should the caching layer (items 2 & 3) cache? → A: **Warcraft Logs tool-call results**, keyed by tool name + arguments with a time-to-live, to cut latency and Warcraft Logs API-point spend on repeat lookups and power "quick access".
- Q: How is self/friend/guild focus scope decided? → A: **Agent infers it from the question's phrasing** (instruction-driven); there is no user-facing scope toggle. Self/friend/guild-referential wording triggers focus; population-level/unrelated wording does not.
- Q: What cache freshness window should results use? → A: **Two tiers.** Immutable report-scoped lookups (fights/tables/events/graphs/player-details for a specific report) are cached long (~24h); volatile current-season leaderboard/ranking lookups are cached short (~1h).
- Q: Which artifact kinds are in scope for this feature? → A: **Interactive charts/plots only** for this feature; the artifact transport is designed extensibly so other kinds (tables, cards) can be added later without rework. Markdown tables continue to render as today.
- Q: Which model runs the background spec-guide task (given web search is only wired to Gemini)? → A: **Always a web-search-capable (Gemini) model**, independent of the user's selected chat model, so guides are always web-sourced.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Personal, friend, and guild context (Priority: P1)

The user records who they are in-game (a personal "main" character), the friends they raid with (friend characters), and their one main guild. Once set, the assistant treats these as standing context: when a question is about the user's own performance, their friends, or their guild, the assistant answers with those characters/guild in focus without the user re-typing names every time — while still answering unrelated, population-level questions normally.

**Why this priority**: This personalization is the backbone of Phase 4 and what most of the other stories build on (the spec-guide background task and the guild-focused answers depend on it). It transforms the assistant from a generic leaderboard tool into "my guild's analyst," which is the headline value of this phase.

**Independent Test**: Add a self character, one or more friend characters, and a main guild; ask "how am I doing?" and "how is our guild performing?" and confirm the assistant resolves those to the saved character/guild without being given names in the prompt; then ask an unrelated population question ("how are Marksmanship Hunters doing overall?") and confirm it answers normally without forcing the guild filter.

**Acceptance Scenarios**:

1. **Given** no profile is set, **When** the user opens the profile area, **Then** they can add a personal character, add friend characters, and set exactly one main guild (name plus the server/region needed to identify it).
2. **Given** a personal character is saved, **When** the user asks a self-referential question ("how are my parses?"), **Then** the assistant uses the saved character as the subject without the user naming it.
3. **Given** friend characters are saved, **When** the user asks about "my friends" / "us", **Then** the assistant can resolve those saved characters.
4. **Given** a main guild is saved, **When** the user asks a guild-scoped question ("how did we do this week?"), **Then** the answer is focused on that guild's members/logs.
5. **Given** a main guild is saved, **When** the user asks an unrelated population question, **Then** the answer is NOT incorrectly narrowed to the guild.
6. **Given** a profile already has a main guild, **When** the user sets a different main guild, **Then** the single-main-guild limit is enforced (the new guild replaces the old, with the change made clear).
7. **Given** saved characters/guild, **When** the user edits or removes an entry, **Then** the change is persisted and reflected in subsequent answers.

---

### User Story 2 - Interactive plots & artifacts in chat (Priority: P1)

When the analysis is best shown visually (a DPS-over-time curve, a spec-comparison bar chart, an ability-breakdown), the assistant renders an interactive chart inline in the chat — the user can hover for exact values, zoom, and read a legend — rather than only a wall of numbers or a static image.

**Why this priority**: Interactive visuals are the most-requested capability of this phase and dramatically raise the perceived quality and usefulness of answers. It is independently valuable: even with no other Phase 4 work, interactive charts make existing analyses far more legible.

**Independent Test**: Ask a question whose answer benefits from a chart (e.g. "plot the raid DPS over time for this pull" or "compare every Mage spec on this boss"); confirm an interactive chart renders inline in the reply, supports hover/zoom, and that the surrounding text answer is still present and consistent with the chart.

**Acceptance Scenarios**:

1. **Given** an answer that warrants a visualization, **When** the reply renders, **Then** an interactive chart appears inline in the chat alongside the text.
2. **Given** an interactive chart is shown, **When** the user hovers a data point, **Then** exact values are shown; **when** they zoom/pan, **Then** the chart responds without a page reload.
3. **Given** a chart is streamed as part of a reply, **When** the chart data is incomplete mid-stream, **Then** the chat never shows broken/garbled chart markup (the chart appears only once its data frame is complete).
4. **Given** multiple charts in one answer, **When** the reply renders, **Then** each renders independently and remains readable on both wide and narrow widths.
5. **Given** a chart could not be produced for a given request, **When** the reply renders, **Then** the user still gets the text answer and a clear note rather than a broken chart.
6. **Given** a rendered chart, **When** the conversation is reopened later, **Then** the chart still renders from stored data (it is not lost on reload).

---

### User Story 3 - Correct rendering of math/LaTeX in answers (Priority: P1)

When the assistant includes a mathematical expression or formula (e.g. a rotation written as a formula, a percentile formula, or an inline fraction), it renders as properly typeset math rather than raw markup like `$$\text{...}$$`.

**Why this priority**: This is a visible rendering defect — answers currently leak raw LaTeX source, which looks broken and undermines trust. It is small, self-contained, and improves every answer that contains a formula, so it ships alongside the other P1 polish.

**Independent Test**: Prompt the assistant to produce an answer containing both an inline math expression and a display/block equation (e.g. ask it to "write the parse rotation as a formula"); confirm both render as typeset math, not raw `$`/`$$`/`\text{}` source, and that normal prose around them is unaffected.

**Acceptance Scenarios**:

1. **Given** an answer containing a block equation (delimited as display math), **When** it renders, **Then** it appears as typeset math, not raw `$$...$$` source.
2. **Given** an answer containing an inline math expression, **When** it renders, **Then** it appears as typeset inline math within the sentence.
3. **Given** math is produced while the answer is still streaming, **When** tokens arrive, **Then** no broken/flashing partial math artifacts are shown (math renders cleanly once its delimiters are complete).
4. **Given** an answer with no math, **When** it renders, **Then** prose, tables, and links are unaffected by the math feature.
5. **Given** a message containing math, **When** it is exported to PDF, **Then** the math renders legibly in the PDF as well (not raw source).

---

### User Story 4 - Faster repeat analysis via result caching (Priority: P2)

Repeated or overlapping Warcraft Logs lookups return quickly and without re-spending the API budget, because results of individual data lookups are cached and reused. The user experiences noticeably faster answers when exploring the same raid/boss/player across several turns.

**Why this priority**: Speed and API-budget conservation directly affect usability (the Warcraft Logs API is rate/point limited), but it is an optimization of existing behavior rather than a new user-facing capability, so it ranks below the headline P1 stories.

**Independent Test**: Ask a question that triggers several Warcraft Logs lookups, then ask a follow-up that reuses the same underlying lookups (same report/boss/filters); confirm the follow-up returns noticeably faster and the Warcraft Logs rate-limit points spent do not increase for the already-fetched lookups.

**Acceptance Scenarios**:

1. **Given** a data lookup has been performed once, **When** the same lookup (same tool + same arguments) is needed again within its freshness window, **Then** the cached result is reused instead of re-calling Warcraft Logs.
2. **Given** a cached result is reused, **When** the answer is produced, **Then** no additional Warcraft Logs API points are spent for that lookup.
3. **Given** a cached result has exceeded its freshness window, **When** the lookup is needed again, **Then** fresh data is fetched and the cache refreshed.
4. **Given** the same data is needed for several independent sub-questions in one turn, **When** the assistant gathers it, **Then** independent lookups are performed concurrently rather than strictly one-at-a-time.
5. **Given** a cached result would be stale or invalid, **When** it is served, **Then** correctness is never sacrificed (the user never sees wrong/old numbers presented as current without the cache respecting its freshness window).

---

### User Story 5 - Per-message analytic PDF report (Priority: P2)

Each substantial assistant reply carries its own "Download report" affordance that exports just that answer — with the context needed to understand it (the question it answered and any charts/graphs it produced) — as a clean, analytic PDF, so the user can share a single finding without exporting the whole conversation.

**Why this priority**: It extends the existing (conversation-level) PDF export to the far more useful per-finding granularity, but it depends on the PDF rendering pipeline already fixed in the prior phase and on the artifact work (US2) for charts, so it ranks P2.

**Independent Test**: Produce an assistant reply that includes a table, prose, a source link, and a chart; use the per-message "Download report" control on that reply; confirm the resulting PDF contains that answer, the originating question for context, and the chart, rendered cleanly, and does NOT include unrelated other messages.

**Acceptance Scenarios**:

1. **Given** a substantive assistant reply, **When** it renders, **Then** it shows a per-message "Download report" control.
2. **Given** the user triggers the per-message report, **When** it generates, **Then** the PDF includes that reply plus the minimal context needed to understand it (at least the originating user question).
3. **Given** the reply produced charts/graphs, **When** the per-message report generates, **Then** those visuals are included in the PDF.
4. **Given** the per-message report, **When** it generates, **Then** it does NOT include other, unrelated messages from the conversation.
5. **Given** tables, headings, lists, long tokens, and math in the reply, **When** the per-message report generates, **Then** all render legibly with no raw markup or off-page overflow (consistent with the conversation-level export).
6. **Given** generation cannot complete, **When** the user requests it, **Then** they receive a clear failure message rather than a corrupt/empty file.

---

### User Story 6 - Auto-fetched spec guide on lock-in (Priority: P2)

When the user locks in a personal character, a friend character, or the main guild, a background task kicks off that figures out the character's active specialization and compiles a concise playstyle guide (rotation, key stats, talents) for it, saving it so the assistant can lean on it as standing context — without making the user wait on the save.

**Why this priority**: It deepens the personalization from US1 with expert context that sharpens "how do I improve" style answers, but it is an enhancement layered on US1 (which must exist first) and runs in the background, so it ranks P2.

**Independent Test**: Add a personal character and confirm the save returns immediately; shortly after, confirm a spec guide for that character's active spec has been fetched and persisted, and that a subsequent "how do I improve on this spec?" answer reflects guidance from it.

**Acceptance Scenarios**:

1. **Given** the user locks in a character or guild name, **When** the save completes, **Then** the UI returns promptly and does not block on guide generation.
2. **Given** a character is locked in, **When** the background task runs, **Then** it resolves the character's active specialization from Warcraft Logs data and compiles a concise guide for that spec.
3. **Given** the background task completes, **When** the guide is ready, **Then** it is persisted and available to the assistant as context for subsequent answers.
4. **Given** a guide exists for a saved character, **When** the user asks an improvement/rotation question about that character, **Then** the answer draws on the persisted guide.
5. **Given** the background task fails or external sources are unavailable, **When** it errors, **Then** the character/guild is still saved and the assistant degrades gracefully (answers without the guide) rather than losing the profile entry.
6. **Given** a character's active spec later changes, **When** the user re-locks or refreshes that entry, **Then** the guide can be regenerated for the new spec.

---

### Edge Cases

- A character name that resolves to multiple servers/regions must be disambiguated (the profile stores enough identity — name + server + region — to be unambiguous), or the user is prompted to pick.
- A guild-scoped question when the saved guild has no recent logs must return a clear "no recent data for your guild" rather than a silent empty answer or a wrongly-broadened result.
- The assistant must not over-apply the guild filter: clearly population-level or unrelated questions (patch notes, "best spec overall") must not be silently narrowed to guild members.
- An interactive chart whose data payload is very large must be bounded/summarized so it does not bloat storage or stall rendering (consistent with the existing graph-size guard).
- A chart must render cleanly whether it arrives mid-stream or on reload of a stored conversation; incomplete chart data must never render as broken markup.
- Math rendering must not misfire on legitimate non-math uses of `$` (e.g. a dollar amount) — only intended math delimiters should typeset.
- A cached tool result must be keyed so that different arguments (encounter, difficulty, metric, pages, filters) never collide; a cache hit must correspond to exactly the same request.
- Cache freshness must account for the fact that current-season leaderboard data changes over time; stale data must not be presented as current beyond its freshness window.
- The per-message report must still be generatable for a reply whose charts were produced in a prior turn but are referenced by that message.
- The spec-guide background task must be idempotent and must not pile up duplicate guides if the user re-locks the same name repeatedly.
- Locking in a name that cannot be resolved on Warcraft Logs must save the profile entry but record that no guide/active-spec could be determined, surfaced to the user.
- With no profile set at all, every existing behavior must continue to work unchanged (personalization is additive).

## Requirements *(mandatory)*

### Functional Requirements

**Profile & guild context (US1)**

- **FR-001**: The system MUST let the user define a single personal ("self") character, zero or more friend characters, and exactly one main guild, each identified unambiguously (name plus server/region as needed).
- **FR-002**: The system MUST persist the profile globally for the single default tenant (no authentication/accounts in this feature) and MUST allow editing and removing entries.
- **FR-003**: The system MUST enforce the one-main-guild limit: setting a new main guild replaces the previous one.
- **FR-004**: When a question is self-referential, about saved friends, or about the saved guild, the assistant MUST resolve it against the saved profile without requiring the user to retype names.
- **FR-005**: The assistant MUST decide focus scope by inferring it from the question's phrasing (instruction-driven, no user-facing scope toggle): it MUST focus answers on the saved self/friend/guild characters when the question concerns the user, their friends, or their guild, while NOT narrowing clearly unrelated or population-level questions to the guild.
- **FR-006**: With no profile set, all existing behavior MUST remain unchanged (personalization is strictly additive).

**Interactive artifacts/plots (US2)**

- **FR-007**: The system MUST be able to render interactive charts/plots inline in the chat (hover for values, zoom/pan, legend) for answers where a visualization aids understanding. Charts/plots are the ONLY artifact kind in scope for this feature; the artifact transport MUST be designed extensibly so other kinds (tables, cards) can be added later without rework. Markdown tables continue to render as today.
- **FR-008**: Chart content MUST be produced on the backend as structured data and transported to the frontend over the existing streaming channel as a discrete artifact (no literal Model Context Protocol server/client is introduced).
- **FR-009**: Artifacts MUST render only once their data is complete; the chat MUST never display broken or partial chart markup mid-stream.
- **FR-010**: Multiple artifacts in one answer MUST each render independently and remain readable on wide and narrow widths.
- **FR-011**: Rendered artifacts MUST be persisted with their conversation so they re-render when the conversation is reopened.
- **FR-012**: If an artifact cannot be produced, the user MUST still receive the text answer plus a clear note, never a broken chart.

**Math/LaTeX rendering (US3)**

- **FR-013**: The system MUST render inline and block mathematical expressions in assistant answers as typeset math, not raw delimiter/source text.
- **FR-014**: Math MUST render safely during streaming (no broken/flashing partial math before its delimiters are complete).
- **FR-015**: Math rendering MUST NOT corrupt non-math content and MUST avoid typesetting legitimate non-math uses of math delimiters (e.g. currency).
- **FR-016**: Exported PDFs MUST render math legibly rather than as raw source.

**Result caching & faster tool calls (US4)**

- **FR-017**: The system MUST cache the results of Warcraft Logs data lookups keyed by tool name plus arguments, and reuse a cached result for an identical subsequent lookup within a freshness window.
- **FR-018**: A cache hit MUST NOT spend additional Warcraft Logs API points for that lookup.
- **FR-019**: Cached results MUST respect a tiered freshness window and refetch when expired: immutable report-scoped lookups (fights/tables/events/graphs/player-details for a specific report) use a long window (~24h), while volatile current-season leaderboard/ranking lookups use a short window (~1h), so users are never shown stale leaderboard data presented as current beyond that window.
- **FR-020**: The cache key MUST distinguish all arguments that change the result (encounter, difficulty, metric, pages, class/spec filters, report/fight/source ids, etc.) so different requests never collide.
- **FR-021**: Independent data lookups needed for one answer MUST be gatherable concurrently rather than strictly sequentially.

**Per-message analytic PDF report (US5)**

- **FR-022**: Each substantive assistant reply MUST offer a per-message "Download report" control, in addition to any conversation-level export.
- **FR-023**: A per-message report MUST include that reply plus the minimal context needed to understand it (at least the originating user question) and MUST exclude unrelated other messages.
- **FR-024**: A per-message report MUST include the charts/graphs that the reply produced.
- **FR-025**: A per-message report MUST render tables, headings, lists, long tokens, and math legibly with no raw markup or off-page overflow, consistent with the conversation-level export.
- **FR-026**: On failure, the per-message report MUST surface a clear error rather than producing a corrupt/empty file.

**Auto-fetched spec guide (US6)**

- **FR-027**: Locking in a personal/friend character or the main guild MUST start a background task that does not block the save or the UI.
- **FR-028**: The background task MUST resolve the character's active specialization from Warcraft Logs data and compile a concise playstyle guide (rotation, key stats, talents) using the existing web-search grounding capability combined with Warcraft Logs data. The task MUST run on a web-search-capable (Gemini) model regardless of the user's selected chat model, so the guide is always web-sourced.
- **FR-029**: The compiled guide MUST be persisted and made available to the assistant as standing context for subsequent answers about that character/spec.
- **FR-030**: If the background task fails or the character cannot be resolved, the profile entry MUST still be saved, the failure MUST be recorded/surfaced, and the assistant MUST degrade gracefully (answer without the guide).
- **FR-031**: The task MUST be idempotent (re-locking the same name MUST NOT accumulate duplicate guides) and MUST support regeneration when a character's active spec changes.

### Key Entities *(include if feature involves data)*

- **Profile**: The single global (default-tenant) record of the user's identity context: one self character, a list of friend characters, and one main guild. Standing context the assistant consults.
- **Character Reference**: A WoW character identified unambiguously (name + server + region), with an optional resolved active specialization and an associated spec guide. Used for self and friend entries.
- **Guild Reference**: The one main guild (name + server + region) used to scope guild-focused answers.
- **Spec Guide**: A persisted, concise playstyle guide (rotation/stats/talents) for a character's active spec, compiled in the background and injected as agent context; relates to a Character Reference.
- **Artifact**: A renderable, interactive piece of an answer (primarily a chart/plot expressed as structured figure data), transported over the streaming channel and persisted with its conversation/message for re-rendering.
- **Cached Tool Result**: A stored Warcraft Logs lookup result keyed by tool name + arguments, with a freshness window, reused to avoid latency and API-point spend.
- **Per-message Report**: An analytic PDF scoped to a single assistant reply plus the minimal context (originating question, produced artifacts) needed to understand it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With a profile set, 100% of clearly self/friend/guild-referential questions are answered against the saved characters/guild without the user retyping names, and 0 clearly population-level questions are wrongly narrowed to the guild.
- **SC-002**: The user can add a self character, at least one friend character, and one main guild, and the one-main-guild limit is enforced in 100% of attempts.
- **SC-003**: Answers that warrant a chart render an interactive chart inline (hover + zoom) in 100% of those cases, and charts re-render correctly after reopening the conversation.
- **SC-004**: No answer ever displays broken/partial chart markup or raw math source (`$$`, `\text{}`) while or after streaming, in 100% of observed answers containing charts or math.
- **SC-005**: For a sequence of turns reusing the same underlying Warcraft Logs lookups, repeated lookups incur zero additional API-point spend and the follow-up answer is measurably faster (reduced lookup latency) versus the first.
- **SC-006**: A per-message report contains exactly the target reply plus its originating question and produced charts, excludes unrelated messages in 100% of exports, and renders with zero instances of raw markup or off-page overflow.
- **SC-007**: Locking in a character returns the save in under ~1 second (non-blocking), and a spec guide for that character's active spec is persisted shortly after and demonstrably influences a subsequent improvement/rotation answer.
- **SC-008**: Every existing capability continues to work unchanged when no profile is set (additive personalization, zero regressions).

## Assumptions

- **Single default tenant**: Personalization targets one global profile with no authentication; multi-user accounts/multi-tenancy remain deferred to Phase X. The profile is persisted in the existing datastore.
- **Artifacts over the existing WebSocket**: "MCP" is interpreted as the goal of rendering rich interactive artifacts. The backend produces figure data (e.g. with a Python charting library) and sends it as a discrete artifact frame over the current streaming WebSocket; the frontend renders it with an interactive charting library. No literal Model Context Protocol server/client is built (Simplicity-First; recorded in the plan's Complexity Tracking if any dependency is added).
- **Charts reuse existing data**: Interactive charts are built from data the existing Warcraft Logs tools already return (e.g. the captured time-series/graph data); no new external data source is required.
- **Spec guide source**: The background guide task resolves the character's active spec from Warcraft Logs and compiles the guide using the existing web-search grounding capability plus Warcraft Logs data; the guide is concise, persisted, and injected as context.
- **Caching keys and freshness**: Caching is applied to Warcraft Logs tool-call results keyed by tool name + arguments with a tiered freshness window (immutable report data ~24h, volatile leaderboard ~1h); it is a performance/cost optimization layered on existing tools. It is an **in-process cache** (the app runs as a single process at current scale); cross-restart/cross-process persistence is out of scope (YAGNI) and may be added later behind the same interface.
- **Math rendering**: The assistant already emits standard math delimiters (LaTeX-style `$...$` / `$$...$$`); the fix is to typeset them in the streaming renderer and PDF, not to change how the model writes math.
- **PDF pipeline reuse**: The per-message report reuses the conversation-level PDF rendering pipeline (fixed in the prior phase) and the captured-graph/artifact mechanism; it changes the scope of what is exported (one message + context), not the rendering engine.
- **Parallel tool execution exists**: The agent can already issue parallel tool calls; this feature strengthens concurrency and adds caching rather than introducing parallelism from scratch. Deeper "predefined workflow"/subagent optimizations are a plan-level design choice and may be deferred if caching + existing parallelism meet the speed goal (YAGNI).
- **Builds on prior phases**: This feature builds on the streaming chat, raid tracking, Barnaby persona, graph capture, PDF export, and fantasy UX delivered in Phases 1–3 (assumed complete).
- **Desktop-primary**: Desktop remains the primary target; narrow layouts stay usable, consistent with prior phases.
