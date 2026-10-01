# Feature Specification: Agent App Enhancements (Raid History, Persistence, Web Search, Dynamic Models, PDF Export)

**Feature Branch**: `002-agent-enhancements`

**Created**: 2026-10-01

**Status**: Draft

**Input**: User description (from `todo.txt`):
"1. Keep track of raid encounters I have previously asked about — give date/time on the UI and sort by that so I know which raids I'm looking at. When I click the specific raid encounter it must automatically start a new chat, sending the AI a prompt like 'Please investigate this raid and highlight any important findings'. Store this in the postgres DB. 2. SessionId and chat messages and responses must also be saved to the db. 3. Add a web-search subagent as a tool to the agent. 4. The available models must be dynamically fetched from the available gemini and anthropic models on vertex. If there is a 'health check' api, test with that, otherwise just try with a 'hello' message and see if the llm responds. 5. Download PDF report with graphs and stuff."

> This feature builds directly on `001-streaming-chat-frontend` (the existing streaming chat app, FastAPI backend, PostgreSQL store, React frontend, and the reused `wcl_agent` core). These are five distinct but related enhancements to that app, delivered as independent user stories.

## Clarifications

### Session 2026-10-01

- Q: What counts as a "raid encounter" to track, and how is it captured? → A:
  Track at the **Warcraft Logs report (raid-night log) level**, captured
  **automatically** whenever a conversation references a report. Each tracked raid
  records the report identifier, a human-readable label (guild/zone/date when
  available), and the time the user last asked about it.
- Q: What should the downloadable PDF contain? → A: A report for the **currently
  open conversation** — the agent's written analysis plus the Warcraft Logs
  **graphs/visuals** it retrieved during that conversation, with a title/header
  identifying the raid and generation date.
- Q: When should a raid be recorded in the tracked-raids list? → A: Only when the
  agent **successfully retrieves report data** via a Warcraft Logs tool call — the
  log is verified accessible and its label (guild/zone/date) is resolved from the
  fetched data. A mere mention (typo or hypothetical) does not create an entry.
- Q: How should the agent get web access ("web-search subagent as a tool")? → A:
  **Model-native grounding** (e.g., built-in Google Search grounding for Gemini
  models on Vertex). Where the selected model does not support native grounding
  (e.g., Anthropic models), web search is simply unavailable for that model and the
  agent degrades gracefully.
- Q: Where should the tracked-raids list live in the UI? → A: As a **separate
  section within the existing left sidebar** (distinct from the conversations
  list), since a raid is a different entity from a chat and may relate to several
  conversations.
- Q: When should model discovery + responsiveness validation run? → A: **At backend
  startup only** — the validated model set is computed once when the backend starts
  and served from there; it refreshes on the next restart. (Simplest; acceptably
  fresh for a single-user local/low-volume app.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Revisit tracked raids and one-click re-investigate (Priority: P1)

As a user who has asked the agent about several raid nights over time, I see a
list of the raids I've previously looked at — each showing when I last asked about
it — sorted so the most recent is easy to find. When I click a raid, the app
immediately opens a **new chat** and sends the agent a kickoff prompt asking it to
investigate that raid and highlight important findings, so I get a fresh analysis
without retyping anything.

**Why this priority**: This is the headline new capability — it turns one-off
questions into a durable, browsable catalog of the user's raids and makes
re-analysis a single click. It is the most visible user value in this batch.

**Independent Test**: Ask the agent about a specific raid log; confirm that raid
appears in the raid list with a timestamp. Ask about a second raid; confirm both
are listed, most-recent-first. Click the first raid; confirm a brand-new
conversation opens and the agent automatically begins investigating that raid and
surfacing findings.

**Acceptance Scenarios**:

1. **Given** the user has asked the agent about a raid log, **When** that
   conversation references the log, **Then** the raid is recorded (or its
   last-asked timestamp updated) and appears in the raid list.
2. **Given** several tracked raids exist, **When** the user views the raid list,
   **Then** each raid shows a readable label and the date/time it was last asked
   about, ordered most-recent-first.
3. **Given** a raid in the list, **When** the user clicks it, **Then** a new
   conversation is created and a kickoff prompt ("Please investigate this raid and
   highlight any important findings") is sent to the agent for that raid, with the
   response streaming as normal.
4. **Given** the user asks about the same raid again later, **When** the new
   reference is recorded, **Then** the existing entry's timestamp updates (no
   duplicate entry) and it moves to the top of the list.
5. **Given** tracked raids exist, **When** the backend is restarted, **Then** the
   raid list is still present and unchanged (persisted in the database).

---

### User Story 2 - Durable sessions and complete chat persistence (Priority: P1)

As a user, I want every conversation — its session identifier, my messages, and
the agent's responses — reliably saved to the database, so that reopening a
conversation after a restart restores not just the visible history but also the
agent's working context, and nothing I asked or received is lost.

**Why this priority**: Persistence is foundational to the whole app's value over
time and underpins the raid-history feature (US1). The current app stores visible
messages but the agent's session context is in-memory only and is lost on restart;
closing that gap is essential for a trustworthy tool.

**Independent Test**: Hold a multi-turn conversation that builds on earlier
context; restart the backend; reopen the conversation and confirm (a) the full
message history is shown and (b) a follow-up question that relies on earlier
context is answered correctly, proving the session/context was restored — not just
the transcript.

**Acceptance Scenarios**:

1. **Given** a conversation, **When** the user sends a message and the agent
   responds, **Then** the session identifier, the user message, and the agent
   response are all persisted to the database.
2. **Given** a persisted conversation, **When** the backend restarts and the user
   reopens it, **Then** the complete message history is displayed.
3. **Given** a reopened conversation after a restart, **When** the user asks a
   follow-up that depends on earlier turns, **Then** the agent answers with the
   earlier context taken into account (context is restored, not just the
   transcript).
4. **Given** a streamed response is interrupted, **When** the stream ends, **Then**
   whatever content was produced is persisted (no silent loss) and clearly
   distinguishable from a completed response.

---

### User Story 3 - Agent can search the web (Priority: P2)

As a user, I want the agent to be able to look things up on the web (for example,
current class guides, patch notes, or boss strategies) as part of answering, so
its analysis isn't limited to Warcraft Logs data alone.

**Why this priority**: Expands the agent's usefulness beyond raw log data, but the
core log-analysis experience is already valuable without it, so it ranks below the
foundational persistence and history work.

**Independent Test**: Ask the agent a question that requires information not in
Warcraft Logs (e.g., "What changed for hunters in the latest patch?"); confirm the
agent invokes a web-search capability and incorporates the retrieved information
into its answer, with the tool activity visible in the stream as other tools are.

**Acceptance Scenarios**:

1. **Given** a question needing external/current information, **When** the agent
   determines a web lookup is useful, **Then** it performs a web search and uses
   the results in its response.
2. **Given** the agent used grounded web information, **When** the response is
   shown, **Then** the UI indicates external information was used (consistent with
   how other tool/agent activity is surfaced).
3. **Given** the selected model lacks native grounding, or a grounded lookup fails
   or returns nothing useful, **When** the agent continues, **Then** it degrades
   gracefully (answers from available data and/or tells the user web information
   wasn't available) rather than erroring out.

---

### User Story 4 - Dynamic, validated model selection (Priority: P2)

As a user choosing which model powers the agent, I want the model list to reflect
the Gemini and Anthropic models actually available to the project on Vertex, and
to only offer models that are currently responsive, so I never pick a model that
silently fails.

**Why this priority**: Removes manual maintenance of a hard-coded model list and
prevents a frustrating failure mode (selecting an unavailable model). Valuable but
secondary to the core persistence/history work.

**Independent Test**: Open the model selector and confirm the offered models match
the Gemini/Anthropic models available on Vertex for the project; temporarily make a
model unavailable and confirm it is excluded (or marked unavailable) rather than
offered as working.

**Acceptance Scenarios**:

1. **Given** the app is running, **When** the user opens the model selector,
   **Then** the listed models are derived from the Gemini and Anthropic models
   available to the project on Vertex (not a static hard-coded list).
2. **Given** the set of available models, **When** the list is produced, **Then**
   each offered model has been verified as responsive — via a health-check
   capability if one exists, otherwise via a minimal "hello" probe that confirms
   the model replies.
3. **Given** a model is unavailable or fails its responsiveness check, **When** the
   list is produced, **Then** that model is excluded from (or clearly marked
   unavailable in) the selectable set.
4. **Given** discovery or validation cannot run (e.g., Vertex is unreachable),
   **When** the user opens the selector, **Then** the app falls back to a sensible
   default model set and the user is informed, rather than showing an empty list.

---

### User Story 5 - Download a PDF report with graphs (Priority: P3)

As a user, after the agent has analyzed a raid, I want to download a PDF of that
analysis — including the Warcraft Logs graphs and visuals it produced — so I can
share or archive the findings outside the app.

**Why this priority**: A valuable convenience for sharing/archiving results, but
not required for the core interactive analysis experience; it ships last.

**Independent Test**: Hold a conversation in which the agent produces analysis and
retrieves graphs for a raid; trigger "download PDF"; confirm a PDF is produced
containing the written analysis and the graphs, with a header identifying the raid
and the generation date.

**Acceptance Scenarios**:

1. **Given** an open conversation with agent analysis, **When** the user requests a
   PDF download, **Then** a PDF is generated and downloaded to the user's device.
2. **Given** the conversation includes Warcraft Logs graphs/visuals, **When** the
   PDF is generated, **Then** those graphs are embedded in the PDF alongside the
   written analysis.
3. **Given** a generated PDF, **When** the user opens it, **Then** it includes a
   header identifying the raid/conversation and the date it was generated.
4. **Given** PDF generation fails, **When** the user requested it, **Then** they
   see a clear error message and the app remains usable (no crash, no partial
   download presented as complete).

---

### Edge Cases

- **Ambiguous or missing raid reference**: if a conversation never clearly
  references a raid log, nothing is added to the raid list (no spurious entries).
- **Raid label unavailable**: if guild/zone/date metadata can't be resolved for a
  tracked raid, it still appears with its identifier and last-asked timestamp.
- **Clicking a raid whose log is no longer accessible**: the new chat opens and the
  agent reports clearly that the raid data could not be retrieved, rather than
  stalling.
- **Restart mid-stream**: an in-progress response that is cut off by a restart is
  persisted as partial and is not shown as a completed answer.
- **Model without native grounding selected**: the agent continues using Warcraft
  Logs data and (when relevant) tells the user web information wasn't available for
  that model.
- **No models pass validation**: the selector never shows an empty list — a
  documented default set is offered with a clear notice.
- **PDF with no graphs**: if the conversation produced no graphs, the PDF still
  generates with the written analysis only.
- **Very large PDF / many graphs**: generation completes within a reasonable time
  without freezing the interface, or the user is told it's being prepared.

## Requirements *(mandatory)*

### Functional Requirements

**Raid history (US1)**

- **FR-001**: The system MUST automatically record a tracked raid when the agent
  **successfully retrieves report data** for a Warcraft Logs report during a
  conversation, capturing the report identifier, a human-readable label
  (guild/zone/date resolved from the fetched data), and a last-asked timestamp. A
  report that is only mentioned but never successfully retrieved MUST NOT create an
  entry.
- **FR-002**: The system MUST avoid duplicate raid entries — referencing an
  already-tracked raid MUST update its last-asked timestamp instead of creating a
  new entry.
- **FR-003**: The system MUST present the tracked raids as a distinct section within
  the existing left sidebar (separate from the conversations list), showing each
  raid's label and last-asked date/time, ordered most-recent-first.
- **FR-004**: When the user selects a tracked raid, the system MUST create a new
  conversation and automatically send the agent a kickoff prompt instructing it to
  investigate that raid and highlight important findings, with the response
  streaming as for a normal message.
- **FR-005**: Tracked raids MUST persist in the database across browser sessions
  and backend restarts.

**Persistence & sessions (US2)**

- **FR-006**: The system MUST persist, for every conversation, its session
  identifier along with all user messages and all agent responses.
- **FR-007**: The system MUST restore a conversation's full message history when it
  is reopened after a backend restart.
- **FR-008**: The system MUST restore the agent's working context for a reopened
  conversation so that follow-up questions account for earlier turns (not only the
  visible transcript).
- **FR-009**: The system MUST persist partial output from an interrupted response
  and keep it distinguishable from a completed response (no silent loss).

**Web search tool (US3)**

- **FR-010**: The agent MUST be able to use web information when answering questions
  that benefit from external or current information, via the model's **native
  grounding/web-search capability** (e.g., Google Search grounding for Gemini
  models on Vertex).
- **FR-011**: When a grounded web lookup occurs, the UI MUST indicate that external
  information was used, consistent with how other tool/agent activity is surfaced.
- **FR-012**: When the selected model does not support native grounding, or a
  grounded lookup fails or returns nothing useful, the agent MUST degrade
  gracefully — answering from available Warcraft Logs data and/or informing the
  user that web information wasn't available — rather than erroring out.

**Dynamic model discovery (US4)**

- **FR-013**: The set of selectable models MUST be derived dynamically from the
  Gemini and Anthropic models available to the project on Vertex, rather than a
  static hard-coded list. Discovery and validation run **once at backend startup**;
  the resulting set is served until the next restart.
- **FR-014**: Each model offered to the user MUST be verified as responsive —
  using a health-check capability if available, otherwise a minimal "hello" probe
  that confirms the model replies.
- **FR-015**: Models that are unavailable or fail validation MUST be excluded from
  (or clearly marked unavailable in) the selectable set.
- **FR-016**: If model discovery or validation cannot run, the system MUST fall
  back to a documented default model set and inform the user, never presenting an
  empty selector.

**PDF export (US5)**

- **FR-017**: The user MUST be able to download a PDF report for the currently open
  conversation.
- **FR-018**: The PDF MUST include the agent's written analysis and any Warcraft
  Logs graphs/visuals produced during that conversation.
- **FR-019**: The PDF MUST include a header identifying the raid/conversation and
  the date it was generated.
- **FR-020**: On PDF generation failure, the system MUST show a clear error and
  remain usable, never presenting a partial file as complete.

**Cross-cutting**

- **FR-021**: All new persisted data (tracked raids, sessions) MUST follow the
  existing single-user, no-auth model of the app (belonging to the single local
  user) and reuse the existing configuration/secret sources.

### Key Entities *(include if feature involves data)*

- **Tracked Raid**: a Warcraft Logs report the user has asked about. Attributes:
  report identifier, human-readable label (guild/zone/date when resolvable),
  first-seen timestamp, last-asked timestamp. Ordered by last-asked for display;
  may link to the conversation(s) that referenced it.
- **Session**: the agent's conversation context/state, identified by a session
  identifier and associated with a Conversation; persisted so it can be restored
  after a restart. (Extends the existing Conversation/Message model from feature
  001.)
- **PDF Report** *(generated artifact, not stored state)*: a document produced on
  demand from a Conversation, containing the written analysis, embedded graphs, and
  an identifying header.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a user asks about a raid, that raid appears in the raid list
  with a correct last-asked timestamp 100% of the time, and repeat references never
  create duplicates.
- **SC-002**: Clicking a tracked raid opens a new conversation and begins a
  streamed investigation of that raid with no manual typing, every time.
- **SC-003**: 100% of conversations — session, user messages, and agent responses
  — remain retrievable after a backend restart, with full history intact.
- **SC-004**: After a restart, a follow-up question that depends on earlier context
  is answered correctly in a reopened conversation (context restoration verified,
  not just transcript display).
- **SC-005**: For questions that require external information, the agent uses web
  search and incorporates the results, with the tool activity visible in the UI.
- **SC-006**: Every model offered in the selector is confirmed responsive at the
  time the list is produced; an unavailable model is never offered as working.
- **SC-007**: The user can download a PDF of an analyzed conversation that contains
  the written analysis and its graphs, with an identifying header and generation
  date.
- **SC-008**: No user-visible crash occurs when any enhancement's dependency is
  unavailable (web search, Vertex discovery, PDF generation) — each degrades with a
  clear message.

## Assumptions

- **Builds on feature 001**: this feature extends the existing streaming chat app
  (FastAPI backend, PostgreSQL store, React frontend, reused `wcl_agent` core).
  Existing conversation/message persistence is reused and extended rather than
  rebuilt.
- **Single user, no auth** (unchanged from 001): all tracked raids and sessions
  belong to the one local user; no multi-user separation.
- **Raid granularity**: raids are tracked at the Warcraft Logs report level and
  captured automatically from conversation references (per clarification); an
  encounter/boss-level breakdown is out of scope for this iteration.
- **Web search via native grounding**: web access is provided through the model's
  native grounding (e.g., Gemini's Google Search grounding on Vertex) rather than a
  separate external search API. This is model-dependent: models without native
  grounding (e.g., Anthropic) simply operate without web access. No separate
  search-provider credential is introduced.
- **Model discovery scope**: discovery targets the Gemini and Anthropic model
  families available to the project on Vertex; validation uses a health-check if the
  provider exposes one, otherwise a minimal "hello" probe. Discovery + validation
  run **once at backend startup** and the validated set is served until the next
  restart (no per-request probing; refresh = restart).
- **PDF scope**: the PDF covers the currently open conversation (written analysis +
  retrieved graphs). Multi-conversation or scheduled/batch reports are out of scope.
- **Credentials & deployment** (unchanged from 001): Google auth via Application
  Default Credentials; secrets from the root `.env` locally and Secret Manager in
  production; no new committed credential files.

## Dependencies

- Feature `001-streaming-chat-frontend` (the app being extended) and its existing
  database schema, agent runner, and streaming protocol.
- The existing `wcl_agent` core and its Warcraft Logs tool set, including the report
  graph/visual retrieval used by the PDF export.
- Valid Warcraft Logs API credentials and Vertex (Gemini/Anthropic) access from the
  existing configuration.
- Model-native grounding support on Vertex (e.g., Gemini Google Search grounding)
  for the web-access capability.
- A PDF generation capability for the export feature.
