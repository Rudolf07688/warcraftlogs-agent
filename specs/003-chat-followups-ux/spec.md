# Feature Specification: Chat Follow-ups & UX Enhancements

**Feature Branch**: `003-chat-followups-ux`

**Created**: 2026-10-01

**Status**: Draft

**Input**: User description: "1. Agent must be able to predict follow-up questions the user might want to know, for example 'What are the parse scores for everyone?', and then render buttons (max 3) for the user to click to further prompt the agent. 2. Confirm parallel tool calls - make better - shared disk space for tool output the agent can pick up when done. 3. Fix chat window rendering where response panel sizes seem fixed. 4. Your name is 'Barnaby' the tavern / innkeeper. See your prompt. You can't be overly nice and must emphasize the mistakes (in a fun way of course). 5. New background image `frontend/dist/assets/morgan-howell-img-1760.jpg`. Use that as the new background but keep it in and make it togglable from config. 6. Resizable side panel."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Suggested follow-up questions (Priority: P1)

After the agent answers a question, the user sees up to three clickable suggestion buttons offering likely next questions (e.g. "What are the parse scores for everyone?", "How do I improve my rotation?", "Why did we wipe on that pull?"). Clicking a suggestion sends it as the next prompt, so the user can keep exploring without typing.

**Why this priority**: This is the headline capability of the feature. It turns a single answer into a guided conversation, reduces typing friction, and surfaces the assistant's analytical range to users who don't know what to ask next. It is independently valuable even if nothing else ships.

**Independent Test**: Ask any analytical question, confirm the response renders with up to three relevant, context-aware suggestion buttons, click one, and verify it is submitted verbatim as the next user message and answered.

**Acceptance Scenarios**:

1. **Given** the agent has produced an answer, **When** the response finishes rendering, **Then** between zero and three follow-up suggestion buttons appear beneath it, each a short natural-language question relevant to the answer just given.
2. **Given** follow-up suggestions are shown, **When** the user clicks one, **Then** that suggestion text is submitted as the next user prompt and the agent responds to it.
3. **Given** the agent has no meaningful follow-ups to offer (e.g. a greeting or error), **When** the response renders, **Then** no suggestion buttons are shown rather than low-value filler.
4. **Given** a suggestion would exceed three, **When** suggestions render, **Then** no more than three buttons are ever displayed.
5. **Given** a new response arrives, **When** it renders, **Then** suggestion buttons from previous turns are not duplicated or left stale on the active turn.

---

### User Story 2 - Reliable parallel tool execution with shared scratch space (Priority: P2)

When a question requires several independent Warcraft Logs lookups (comparing specs, several encounters, a full-raid scan), the agent issues those tool calls concurrently and reliably collects every result once each finishes, including large outputs, without results being lost, truncated, or silently dropped.

**Why this priority**: Parallel lookups already exist but are unconfirmed and can lose or garble output; correctness of multi-lookup answers depends on this. It is foundational to the quality of comparison and raid-wide answers but is not user-visible on its own, so it ranks below the headline feature.

**Independent Test**: Ask a question that triggers multiple concurrent tool calls (e.g. "compare these three specs"), confirm all calls run concurrently, and verify every tool's output is present and complete in the agent's final answer with none missing.

**Acceptance Scenarios**:

1. **Given** a question needing several independent lookups, **When** the agent runs them, **Then** the lookups execute concurrently rather than strictly one after another.
2. **Given** multiple concurrent lookups complete, **When** the agent composes its answer, **Then** every lookup's result is available to the agent and reflected in the answer.
3. **Given** a tool returns a large result, **When** it is collected, **Then** the full result is preserved (not truncated by in-transit limits) and usable by the agent.
4. **Given** one of several concurrent lookups fails, **When** the others succeed, **Then** the agent still uses the successful results and clearly reports which lookup failed instead of failing the whole turn.

---

### User Story 3 - Correct chat window and response panel sizing (Priority: P2)

The chat area and response panels size themselves to their content and the available window space, growing and shrinking naturally as messages are added and as the window or panels are resized, instead of being stuck at a fixed size.

**Why this priority**: A broken layout undercuts every other improvement and makes long answers hard to read. It is a visible defect affecting all users on every turn, so it ranks just below the headline feature.

**Independent Test**: Send short and very long responses, resize the browser window, and confirm the response panels reflow to fit content and available space without clipping, overflow, or a fixed/locked height.

**Acceptance Scenarios**:

1. **Given** a long agent response, **When** it renders, **Then** the response panel expands to show it (with normal scrolling of the conversation) rather than clipping to a fixed height.
2. **Given** the browser window is resized, **When** the layout updates, **Then** the chat and response area reflow to use the available space.
3. **Given** a short response, **When** it renders, **Then** the panel does not reserve excessive empty fixed space around it.

---

### User Story 4 - Barnaby the innkeeper persona (Priority: P3)

The assistant introduces and refers to itself as "Barnaby", a tavern innkeeper and guild MC. Barnaby is warm and funny but never saccharine: he gives blunt, honest feedback and cheerfully calls out mistakes rather than flattering the user.

**Why this priority**: Persona shapes the product's voice and is a quick, self-contained change, but it does not alter analytical capability, so it ranks below behavior and layout fixes.

**Independent Test**: Start a conversation and ask the assistant who it is; confirm it identifies as Barnaby the innkeeper, and that when reviewing a weak parse it points out the mistakes plainly in a good-humored way rather than only praising.

**Acceptance Scenarios**:

1. **Given** the user asks the assistant's name or for an introduction, **When** it responds, **Then** it identifies as "Barnaby" the tavern/innkeeper.
2. **Given** the user shares performance data with clear mistakes, **When** Barnaby responds, **Then** he explicitly names the mistakes and gives blunt advice, framed with humor rather than harshness or empty niceness.
3. **Given** any normal answer, **When** Barnaby responds, **Then** the innkeeper voice is consistent without sacrificing the accuracy and data-grounding of the analysis.

---

### User Story 5 - Resizable side panel (Priority: P3)

The user can drag to resize the side panel to a width that suits them, and that width is remembered for later visits.

**Why this priority**: A quality-of-life layout control that improves readability of both the side panel and the main chat, but it is not essential to core functionality.

**Independent Test**: Drag the side panel's edge to a new width, confirm the main content reflows accordingly, reload the app, and verify the chosen width persists.

**Acceptance Scenarios**:

1. **Given** the side panel is visible, **When** the user drags its edge, **Then** its width changes smoothly and the main chat area reflows to fill the remaining space.
2. **Given** the user has resized the side panel, **When** they reload or revisit the app, **Then** the previously chosen width is restored.
3. **Given** the user drags toward the extremes, **When** resizing, **Then** the panel is constrained within sensible minimum and maximum widths so it never becomes unusable or hides the chat.

---

### User Story 6 - Togglable background image (Priority: P3)

The application uses the new background image (`morgan-howell-img-1760.jpg`) by default, and the previous background remains available; a configuration setting controls which background is shown.

**Why this priority**: Visual refresh with a fallback option; purely cosmetic and the lowest-risk item, so it ranks last.

**Independent Test**: Load the app and confirm the new image is the background by default; change the background configuration setting and confirm the displayed background switches, with the previous background still selectable.

**Acceptance Scenarios**:

1. **Given** default configuration, **When** the app loads, **Then** the new `morgan-howell-img-1760.jpg` image is shown as the background.
2. **Given** the background setting is changed, **When** the app renders, **Then** the displayed background reflects the selected option.
3. **Given** the previous background is retained, **When** a user selects it via the setting, **Then** the old background is shown and legibility of chat content is preserved over either background.

---

### Edge Cases

- Follow-up suggestions must remain readable and tappable on narrow/mobile widths and not overflow the message area.
- A suggestion clicked while the agent is still responding to a prior turn should be queued or disabled rather than interleaving two turns.
- Suggestions that are overly long should be truncated for display while still submitting the full question text.
- When a parallel lookup is slow, the overall turn should not hang indefinitely; a timeout or clear partial-result behavior applies.
- Resizing the side panel very small must not permanently hide the control used to resize it again.
- If the configured background image is missing or fails to load, the app falls back to a solid/legible background rather than breaking layout.
- Switching backgrounds must preserve text contrast so chat content stays readable.

## Requirements *(mandatory)*

### Functional Requirements

#### Follow-up suggestions

- **FR-001**: The system MUST generate up to three context-relevant follow-up questions tied to the content of each agent answer.
- **FR-002**: The system MUST render these follow-ups as clickable buttons beneath the agent's response, displaying no more than three.
- **FR-003**: Clicking a follow-up button MUST submit that question's full text as the next user prompt and trigger a normal agent response.
- **FR-004**: The system MUST omit follow-up buttons entirely when no meaningful suggestions apply (e.g. greetings, errors, trivial replies).
- **FR-005**: Follow-up buttons MUST be associated with the turn that produced them and not persist as stale/active controls on later turns.

#### Parallel tool execution

- **FR-006**: The system MUST execute independent tool lookups for a single turn concurrently rather than strictly sequentially.
- **FR-007**: The system MUST reliably collect the complete output of every concurrent tool call and make it available to the agent before it composes its answer.
- **FR-008**: The system MUST preserve large tool outputs in full without truncation or loss when collecting results from concurrent calls.
- **FR-009**: When one concurrent tool call fails, the system MUST continue using the successful results and clearly report the failed lookup rather than failing the entire turn.

#### Chat window / response panel rendering

- **FR-010**: Response panels MUST size to their content and the available window space, expanding for long answers and contracting for short ones, rather than using a fixed height.
- **FR-011**: The chat/response area MUST reflow responsively when the browser window is resized.
- **FR-012**: Long responses MUST remain fully readable via normal conversation scrolling without clipping or overflow.

#### Persona

- **FR-013**: The assistant MUST present itself as "Barnaby", a tavern/innkeeper and guild MC, consistently across the conversation.
- **FR-014**: The assistant MUST deliver blunt, honest feedback that explicitly calls out mistakes, framed with good humor rather than flattery or harshness.
- **FR-015**: The persona MUST NOT compromise analytical accuracy or the requirement to ground every answer in tool-returned data.

#### Resizable side panel

- **FR-016**: Users MUST be able to resize the side panel by dragging, with the main content reflowing to fill the remaining space.
- **FR-017**: The system MUST persist the user's chosen side-panel width across sessions.
- **FR-018**: The side-panel width MUST be constrained within sensible minimum and maximum bounds so neither the panel nor the chat becomes unusable.

#### Background image

- **FR-019**: The system MUST display the new `morgan-howell-img-1760.jpg` image as the default background.
- **FR-020**: The system MUST retain the previous background and allow switching between backgrounds via a configuration setting.
- **FR-021**: The system MUST preserve chat-content legibility over whichever background is selected, and fall back gracefully if a background image fails to load.

### Key Entities *(include if data involved)*

- **Follow-up Suggestion**: A short natural-language question tied to a specific agent turn; has display text and the full prompt text submitted on click (0–3 per turn).
- **Agent Turn**: A single user-prompt/agent-response exchange that may carry follow-up suggestions and the collected outputs of one or more tool calls.
- **Tool Call Result**: The complete output of one lookup within a turn, collected via shared scratch space; associated with its originating turn and tool, and may be large.
- **UI Preference**: User-adjustable presentation settings persisted across sessions — currently side-panel width and selected background.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In at least 90% of analytical answers, one to three relevant follow-up suggestions are offered, and clicking any suggestion produces a coherent next answer with no typing required.
- **SC-002**: No agent turn ever displays more than three follow-up buttons.
- **SC-003**: For turns that trigger multiple independent lookups, 100% of successful lookups' results are reflected in the final answer (zero silently dropped results), and such turns complete faster than running the same lookups one at a time.
- **SC-004**: Large tool outputs are delivered to the agent complete, with zero truncation observed across representative multi-lookup scenarios.
- **SC-005**: Response panels correctly fit content across short answers, very long answers, and at least three window widths (narrow, typical, wide) with no clipping, overflow, or fixed-height gaps.
- **SC-006**: When asked, the assistant identifies as Barnaby in 100% of cases, and in reviews of flawed performance it explicitly names at least the primary mistake rather than only praising.
- **SC-007**: Users can resize the side panel and, after reload, the chosen width is restored in 100% of attempts, always within the defined min/max bounds.
- **SC-008**: The new background is shown by default, and toggling the configuration setting switches the displayed background with chat text remaining legible over both options.

## Assumptions

- Follow-up suggestions are produced by the assistant as part of (or alongside) its response for the current turn; a maximum of three are shown and fewer (including none) is acceptable when relevance is low.
- "Shared disk space for tool output" refers to a shared scratch mechanism the backend uses so concurrent tool calls can deposit their (possibly large) outputs for the agent to collect once complete; the exact storage mechanism is an implementation detail decided during planning.
- The background toggle is driven by application configuration with the new image as the default; exposing it as an in-app control is acceptable but the minimum requirement is a configurable default plus retained fallback.
- Side-panel width and background selection are persisted client-side (e.g. per-browser) unless a server-side preference store already exists for the user.
- The persona change is purely to the assistant's voice/instructions and does not alter which tools are available or how data is grounded.
- The new background image already exists at `frontend/dist/assets/morgan-howell-img-1760.jpg` and the previous background remains available in the asset set.
- Existing streaming chat, model selection, and web-search behaviors from prior features remain unchanged except where these requirements touch them.

## Dependencies

- Builds on the existing streaming chat frontend (001) and agent enhancements (002), including the current agent prompt/persona, parallel-lookup guidance, model selection, and side panel.
- Requires the new background asset to be present in the frontend asset pipeline.
