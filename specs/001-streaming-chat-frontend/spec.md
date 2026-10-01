# Feature Specification: Streaming Chat Frontend

**Feature Branch**: `001-streaming-chat-frontend`

**Created**: 2026-10-01

**Status**: Draft

**Input**: User description: "We are adding a frontend to this app to interact with the agent. I want best practice agent <-> frontend streaming protocols such as websockets. The AI message response must gradually appear in the chat as the agent streams back. The python backend must be served as a FastAPI endpoint using asyncio wherever possible. The agent must be able to call multiple tool calls in parallel when retrieving data from warcraftlogs. For now keep the frontend basic. I want to be able to select a model, a chat box interface, dark mode, and a side bar to keep track of previous chats. We will spin up a backend postgres 17 database to keep track of app state over time - please make all of this locally testable with a docker compose file that injects our root .env file into the containers."

## Clarifications

### Session 2026-10-01

- Q: Google auth approach across local dev and future Cloud Run? → A: Application
  Default Credentials (ADC) everywhere — mount the gcloud ADC file locally; use the
  attached service account on Cloud Run. One code path, no keys committed.
- Q: Source of non-Google secrets (WCL id/secret, DB password) on Cloud Run? → A:
  Google Secret Manager, injected as env vars (config stays env-var based; local
  still uses the root `.env`).
- Q: Production database backing (Cloud Run is stateless)? → A: Cloud SQL for
  PostgreSQL 17 in production; local docker Postgres for development (one SQLAlchemy
  code path via `DATABASE_URL`).
- Q: Access control for the public Cloud Run deployment (no app auth yet)? → A:
  Fully public and unauthenticated for now — accepted risk; real access control is a
  later improvement.
- Q: Backend Python version? → A: Python 3.14 (aligns with the constitution).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stream a conversation with the agent (Priority: P1)

A user opens the web app, types a Warcraft Logs question into a chat box, sends it,
and watches the agent's answer appear gradually — word by word / chunk by chunk —
rather than waiting for the whole answer and seeing it all at once. While the agent
is gathering data, the user sees that it is working.

**Why this priority**: This is the core value of the feature and the MVP — a
responsive, live conversation with the analysis agent in the browser. Without it,
nothing else matters.

**Independent Test**: Open the app, ask "How are hunters performing on Heroic
Ula'tek?", and confirm (a) a response begins appearing within a couple of seconds,
(b) the text grows incrementally as it streams, and (c) the completed answer
matches what the agent would produce.

**Acceptance Scenarios**:

1. **Given** the app is open, **When** the user sends a message, **Then** the
   agent's reply begins rendering incrementally before it is fully complete.
2. **Given** the agent is retrieving data, **When** the user is waiting, **Then**
   the UI shows an in-progress / working indication until the answer streams in.
3. **Given** a reply has finished streaming, **When** the user reads it, **Then**
   the full message is displayed and the input is ready for the next question.
4. **Given** a question that needs several Warcraft Logs lookups, **When** the
   agent retrieves the data, **Then** the lookups happen concurrently and the
   answer arrives without unnecessary serial delay.

---

### User Story 2 - Select the AI model (Priority: P2)

A user chooses which AI model powers the agent (for example a newer or faster
model such as "gemini-3.7-flash") from a control in the interface. The selected
model is used for subsequent messages.

**Why this priority**: Model choice materially changes answer quality, speed, and
cost, and the user explicitly wants to switch between models without code changes.

**Independent Test**: Select a model, send a message, and confirm the response is
produced by the chosen model; switch to a different model and confirm the next
message uses the new selection.

**Acceptance Scenarios**:

1. **Given** a set of available models, **When** the user opens the model control,
   **Then** they can see and choose among the available models.
2. **Given** a model is selected, **When** the user sends a message, **Then** that
   model is used to generate the response.
3. **Given** the user changes the model mid-conversation, **When** they send the
   next message, **Then** the new model is applied from that message onward.

---

### User Story 3 - Revisit previous chats from a sidebar (Priority: P2)

A user sees a sidebar listing their previous conversations. Selecting one reopens
it with its full message history. Conversations persist across browser sessions and
backend restarts. The user can start a new conversation at any time.

**Why this priority**: Persistent history makes the tool usable over time and lets
the user return to prior analyses, which is a primary stated requirement.

**Independent Test**: Hold a conversation, start a new one, confirm both appear in
the sidebar; restart the app; confirm both conversations are still listed and
reopening one shows its complete history.

**Acceptance Scenarios**:

1. **Given** past conversations exist, **When** the app loads, **Then** they are
   listed in the sidebar (most recent first).
2. **Given** a conversation in the sidebar, **When** the user selects it, **Then**
   its full message history is displayed in the chat area.
3. **Given** the user is in a conversation, **When** they choose "new chat",
   **Then** a fresh empty conversation starts and is added to the sidebar once used.
4. **Given** the backend is restarted, **When** the user returns, **Then** their
   previous conversations and messages are still available.

---

### User Story 4 - Basic, dark-mode chat interface (Priority: P3)

The interface is intentionally simple: a sidebar, a scrollable message area, and a
message input box, presented in dark mode.

**Why this priority**: Explicitly requested but not blocking core function; a clean
dark basic UI improves usability once the functional pieces work.

**Independent Test**: Load the app and confirm a dark-themed layout with a readable
chat area, an input box, and the conversation sidebar.

**Acceptance Scenarios**:

1. **Given** the app loads, **When** it is first displayed, **Then** it uses a dark
   color theme with readable contrast.
2. **Given** a long conversation, **When** messages exceed the viewport, **Then**
   the message area scrolls and keeps the latest message in view.

---

### Edge Cases

- **Connection loss mid-stream**: if the live connection drops while a reply is
  streaming, the UI indicates the interruption and allows retry; a partial reply is
  not silently presented as complete.
- **Agent/tool error**: if the agent or a Warcraft Logs lookup fails, the user
  sees a clear, friendly message rather than a stall or a raw error.
- **Missing credentials/model unavailable**: if a selected model or required
  credential is unavailable, the user is told clearly and can pick another model.
- **Rapid or empty sends**: empty messages are ignored; sending while a reply is
  still streaming is handled predictably (queued or blocked, not corrupting state).
- **Very long answers / many data lookups**: large responses still stream smoothly
  without freezing the interface.
- **Analysis context**: when a question needs a specific encounter/difficulty that
  the user has not stated, the agent asks for or infers it conversationally.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let a user hold a text conversation with the agent
  through a browser chat interface.
- **FR-002**: Agent responses MUST be delivered to the UI incrementally and
  rendered as they arrive, so the message visibly grows while being produced.
- **FR-003**: The system MUST maintain a live, low-latency channel between the
  frontend and backend for the duration of a streamed response.
- **FR-004**: While the agent is working (e.g. retrieving data), the UI MUST show
  an in-progress indication until output begins streaming.
- **FR-005**: When answering a question that requires multiple Warcraft Logs data
  retrievals, the agent MUST perform those retrievals concurrently rather than one
  after another.
- **FR-006**: The agent MUST retain its full Warcraft Logs analytical capability
  (leaderboard distributions, report deep-dives, character history, and arbitrary
  supported queries) within the chat.
- **FR-007**: The user MUST be able to select which AI model powers the agent, and
  the selection MUST take effect for subsequent messages without code changes.
- **FR-008**: The set of selectable models MUST be configurable, and the system
  MUST accept a model identifier provided at request time.
- **FR-009**: The system MUST display a sidebar listing the user's previous
  conversations, ordered most-recent-first.
- **FR-010**: The user MUST be able to open a previous conversation and see its
  complete message history.
- **FR-011**: The user MUST be able to start a new conversation.
- **FR-012**: Conversations, their messages, and the model used MUST persist across
  browser sessions and backend restarts.
- **FR-013**: The interface MUST present a basic layout (sidebar + message area +
  input box) in a dark theme.
- **FR-014**: The system MUST handle connection interruptions, agent errors, and
  Warcraft Logs failures with clear user-facing messaging and no silent data loss.
- **FR-015**: The entire system MUST be runnable locally for testing via a single
  command, sourcing configuration/secrets from the project's root environment file.
- **FR-016**: The system MUST authenticate to Google services via Application
  Default Credentials in every environment (mounted ADC locally, attached service
  account on Cloud Run) and MUST NOT require any credential file committed to the
  repository.
- **FR-017**: Configuration MUST be read from environment variables so the secret
  source can differ by environment (root `.env` locally, Google Secret Manager on
  Cloud Run) without code changes.

### Key Entities *(include if feature involves data)*

- **Conversation**: a chat session. Attributes: identifier, title/label, created
  and last-updated timestamps, and the model currently associated with it. Has many
  Messages.
- **Message**: one turn in a conversation. Attributes: role (user or agent),
  text content, timestamp, and ordering within the conversation.
- **Model selection**: the chosen AI model identifier associated with a
  conversation and/or request.
- **Analysis context** *(optional)*: the encounter/difficulty a conversation is
  focused on, when the user has specified one.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After sending a message, the user sees the response begin appearing
  within 2 seconds for typical questions.
- **SC-002**: Responses are perceivably incremental — a user can observe the answer
  building up over time rather than appearing all at once.
- **SC-003**: For questions requiring multiple Warcraft Logs lookups, concurrent
  retrieval measurably reduces total answer time compared with retrieving the same
  data one lookup at a time (target: at least 40% faster for a 3+ lookup question).
- **SC-004**: 100% of completed conversations remain retrievable from the sidebar
  after a backend restart, with full message history intact.
- **SC-005**: Changing the selected model is reflected in the very next response
  100% of the time.
- **SC-006**: A developer can bring up the complete stack locally with one command
  and complete an end-to-end streamed conversation, with no manual secret copying
  beyond the existing root environment file.
- **SC-007**: On an interrupted or failed response, the user always receives a
  clear status (error or disconnected) rather than a silent or misleadingly
  "complete" result.

## Assumptions

- **Single user, no authentication** for this iteration: the app is used by one
  person; "previous chats" belong to that single user. Multi-user accounts and login
  are out of scope for v1. The eventual Cloud Run deployment is **fully public and
  unauthenticated** — an explicitly accepted risk for now; adding access control is a
  tracked later improvement, not a v1 requirement.
- **Credentials & deployment targets**: Google auth uses **Application Default
  Credentials** everywhere (locally a mounted gcloud ADC file; on Cloud Run the
  attached **service account**). Production targets **Cloud Run** (backend/frontend),
  **Cloud SQL for PostgreSQL 17** (database), and **Google Secret Manager** (WCL and
  DB secrets injected as env vars). Local development uses docker Postgres and the
  root `.env`. Backend runs on **Python 3.14**.
- **Analysis context is conversational**: to keep the frontend basic (per the
  request), there is no separate encounter-selection menu in the web UI; the user
  states the encounter/difficulty in chat and the agent handles it. (The existing
  terminal menu remains available separately.)
- **Model list**: a small, configurable set of supported model identifiers is
  offered, defaulting to the project's current model; the backend passes the chosen
  identifier through so new models (e.g. "gemini-3.7-flash") can be used by
  configuration alone.
- **Directed technical constraints** (explicitly required by the user; recorded
  here, to be detailed during planning): the backend is served as a FastAPI
  endpoint using asyncio wherever possible; the agent↔frontend streaming uses a
  best-practice real-time protocol such as WebSockets; app state is persisted in a
  PostgreSQL 17 database; and the full stack is locally testable via a Docker
  Compose setup that injects the project's root `.env` into the containers. The
  frontend is React. These align with the project constitution.
- **Scope of "basic frontend"**: functional chat, model selector, dark theme, and
  conversation sidebar — no advanced theming, rich text editing, or multi-pane
  dashboards in v1.
- Existing Warcraft Logs and model credentials from the root environment file are
  reused; no new credential types are introduced.

## Dependencies

- The existing WCL analysis agent and its tool set (the agent being surfaced here).
- Valid Warcraft Logs API credentials and model/provider access from the root
  environment configuration.
- For production: Google Cloud services — Cloud Run (hosting), Cloud SQL for
  PostgreSQL 17 (persistence), and Secret Manager (secrets). Not required for local
  development.
