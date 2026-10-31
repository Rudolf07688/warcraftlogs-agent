# Feature Specification: LLM provider switch and Anthropic API client for the chat agent

**Feature Branch**: `032-llm-provider-switch`

**Created**: 2026-10-31

**Status**: Signed off (scrum master, 2026-10-31; PO decision D9)

**Stories**: sc-249 (5) LLM provider switch (`WCL_LLM_PROVIDER`) and Anthropic API client for the
chat agent. Epic 248 (switchable LLM provider).

**Input**: User description: "LLM provider switch (WCL_LLM_PROVIDER=vertex|anthropic) and Anthropic
API client for the chat agent: one provider layer module is the only place that knows the active
provider and builds model clients; with anthropic the chat agent's Claude models call the Anthropic
API (AsyncAnthropic) through the existing retry wrapper; ANTHROPIC_API_KEY is a secret never logged;
missing key degrades without crashing; API-form vs Vertex-form model ids are told apart in one
place; a chat whose stored model is not served continues on the default; per-provider defaults for
the fixed model roles (default chat, report, guide, guide review, suggest/fast, greeting) with
explicit env winning; docs in .env.example and README; fake-only tests."

**Binding sprint decisions** (`sprints/2026-10-31/decisions.md`): D1 config-only switch plus a
restart (owner review), D2 `anthropic` covers every LLM call (owner review; 032 delivers the agent
side, 035 the non-agent call sites), D4 a chat on an unserved model continues on the default, D5
per-provider model-role defaults with explicit env winning.

**Scope split with the other epic-248 features**: model discovery on the Anthropic Models API,
the cached catalog key and the 429 → sibling path for API ids are 033 (sc-250). The provider label
in the picker is 033 (sc-251). Suggestions, titles, report synthesis and the guide pipeline moving
off `google.genai` are 035 (sc-252, sc-253), built on this feature's provider layer.

## Clarifications

### Session 2026-10-31

- Q: Default chat model under `anthropic`? → A: `claude-sonnet-5-5` (PO, D9). Role defaults
  approved: report and guide author `claude-sonnet-5-5`, guide review `claude-opus-5-5`,
  suggest/fast and greeting `claude-haiku-5-5`. Vertex defaults unchanged.
- Q: An explicit role env value the active provider can't serve (a Gemini id under `anthropic`)? →
  A: Ignored with one warning per role; the provider default is used. An explicit value wins only
  when the active provider can serve it.
- Q: Does 032 make Claude agent turns work on the current models? → A: Yes, both parts, kept to
  the agent factory and the Claude retry wrapper: adaptive thinking for Claude, and every Claude
  request asks the API to drop thinking blocks invalidated by history edits instead of failing.
  This also restores Claude on Vertex. No other thinking or prompt changes.
- Q: Scope of the stale-chat-model fallback? → A: WebSocket chat turns only. The REST endpoints
  (conversation create, raid and M+ investigate) keep their 400 for an unknown model.
- Q: Greeting role override? → A: Add `WCL_GREETING_MODEL`.
- PO condition (D9, AC6 intent for new chats): after a switch the frontend must not send a stale
  model id. If the picker's selection isn't in `/api/models`, it falls back to the default. The
  behaviour exists today (the selection isn't persisted; the app resets to the served default);
  a frontend test proves it without changing the app shell.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Barnaby on Claude with an Anthropic API key (Priority: P1)

The owner has an Anthropic API key and no Vertex Claude quota. They add two lines to `.env`
(`WCL_LLM_PROVIDER=anthropic` and the key) and restart. Barnaby now answers chat turns on Claude
through the Anthropic API: he looks up Warcraft Logs data with his tools over several rounds,
waits and retries when the API says it is busy, and greets new chats as before.

**Why this priority**: It is the story's purpose and the foundation the rest of epic 248 builds on.

**Independent Test**: With a faked Anthropic API client and `WCL_LLM_PROVIDER=anthropic`, run a
chat turn, a greeting and a raid investigation through the normal agent stream. Every model request
reaches the faked API client (never a Vertex client), carries the tool declarations, and a faked
429 is retried by the existing retry loop.

**Acceptance Scenarios**:

1. **Given** `WCL_LLM_PROVIDER=anthropic` and a key, **When** the player sends a chat message,
   **Then** the agent's Claude model calls the Anthropic API, may call tools over several rounds,
   and streams its answer.
2. **Given** the same setup, **When** the API answers 429 or 529 on a request, **Then** the existing
   retry wrapper shows "retrying" and retries within its wait budget, exactly as on Vertex.
3. **Given** the same setup, **When** a new chat opens, **Then** the greeting is generated on the
   greeting role's Claude model.
4. **Given** `WCL_LLM_PROVIDER` is unset or `vertex`, **When** anything runs, **Then** behaviour is
   today's: Gemini and Claude on Vertex, the same clients, the same default models.

---

### User Story 2 - The key stays secret and a missing key never crashes the app (Priority: P1)

The owner trusts that their Anthropic key never shows up anywhere it could leak: not in logs, not
in a chat error, not in any `/api/*` response, not in an exception message. If they switch to
`anthropic` and forget the key, the app still starts, logs one clear error saying what is missing,
and serves the degraded model state instead of crashing.

**Why this priority**: A leaked key is billable by anyone who finds it; a crash on a missing key
blocks the whole app, including the Warcraft Logs features that don't need a model.

**Independent Test**: Set a sentinel key value, drive startup, a failing chat turn (faked auth
error) and the `/api/*` endpoints, capture all log records and frames, and assert the sentinel never
appears. Separately, start with `anthropic` and no key and assert one error line, a degraded model
state, and a running app.

**Acceptance Scenarios**:

1. **Given** a sentinel key, **When** startup, a chat turn that fails with an authentication error,
   and the models, health and greeting endpoints all run, **Then** the sentinel appears in no log
   record, no WebSocket frame, no HTTP response body and no exception text.
2. **Given** `WCL_LLM_PROVIDER=anthropic` and no key, **When** the backend starts, **Then** it logs
   exactly one error naming `ANTHROPIC_API_KEY` as missing, serves the degraded model state, and
   stays up.
3. **Given** the same missing key, **When** the player sends a chat message, **Then** the turn ends
   with the usual friendly error frame, without a traceback or key text, and the socket stays open.

---

### User Story 3 - One `.env` line switches the provider; everything else follows (Priority: P1)

The owner's `.env` already sets Gemini model ids for the default chat model, reports and guides.
Switching to `anthropic` must not require editing six more lines. Each fixed model role (default
chat, report, guide, guide review, suggest/fast, greeting) has a default per provider; an explicit
env value still wins where the active provider can serve it.

**Why this priority**: D1 and D5 promise "one line plus a restart"; without per-provider role
defaults the switch silently keeps Gemini ids that the Anthropic API can't run.

**Independent Test**: With no role variables set, resolve every role under each provider and
compare with the defaults table. With an explicit Claude id set for one role, that id wins under
`anthropic`. With a Gemini id set for a role and `anthropic` active, the role falls back to the
Claude default with one warning.

**Acceptance Scenarios**:

1. **Given** no role variables and `anthropic`, **When** the app resolves the roles, **Then** each
   gets the Anthropic default from the role table (FR-008).
2. **Given** `WCL_REPORT_MODEL=claude-opus-5-5` and `anthropic`, **When** a report runs, **Then** it
   uses `claude-opus-5-5`.
3. **Given** `WCL_DEFAULT_MODEL=gemini-3.6-flash` and `anthropic`, **When** the app starts, **Then**
   it logs one warning that the Gemini id isn't served by the active provider and uses the
   Anthropic default for that role.
4. **Given** an invalid `WCL_LLM_PROVIDER` value such as `openai`, **When** the app starts,
   **Then** it logs one warning and runs as `vertex`.

---

### User Story 4 - Old chats keep working after a switch (Priority: P2)

A chat created on Gemini is reopened after switching to `anthropic` (or the reverse). Its stored
model isn't served any more. The player types a message and the chat simply continues on the active
provider's default model, with no error.

**Why this priority**: Without it, every existing chat breaks after a switch (D4).

**Independent Test**: Under `anthropic`, send a WebSocket turn whose model is a Gemini id and check
that it runs on the default model and that no `invalid_model` frame is sent.

**Acceptance Scenarios**:

1. **Given** `anthropic` is active and a turn arrives naming `gemini-3.6-flash`, **When** the turn
   starts, **Then** it runs on the active default model and no error frame is sent.
2. **Given** `anthropic` is active and a turn names the Vertex form `claude-sonnet-4@20250514`,
   **When** the turn starts, **Then** the id is read in the active provider's form
   (`claude-sonnet-4-20250514`); if that model is served the turn runs on it, otherwise on the
   default.
3. **Given** the picker's selection (or a reopened chat's stored model) isn't in the served list
   after a switch, **When** the player sends a message, **Then** the browser sends the served
   default, never the stale id.
4. **Given** a REST request (new conversation, raid or M+ investigate) names an unserved model,
   **When** it arrives, **Then** it still gets today's 400.

---

### User Story 5 - The owner can follow the switch from the docs (Priority: P3)

`.env.example` and README explain the switch, the key, the role defaults, and that Google
Application Default Credentials aren't needed for LLM calls under `anthropic`. Compose still starts
the backend when no ADC file exists.

**Why this priority**: The switch is configuration only, so the docs are the user interface.

**Independent Test**: Read the `.env.example` provider block and the README section; check that
every variable this feature adds is documented with its default, and that the compose file starts
without an ADC file (reasoned from the mount definition, no live run).

**Acceptance Scenarios**:

1. **Given** a fresh clone, **When** the owner reads `.env.example`, **Then** it shows
   `WCL_LLM_PROVIDER`, `ANTHROPIC_API_KEY` (empty, marked secret) and the role defaults per provider.
2. **Given** `anthropic` and no ADC file on the host, **When** compose starts the backend, **Then**
   it starts and LLM calls don't need ADC.

### Edge Cases

- `WCL_LLM_PROVIDER` with odd case or spaces (`" Anthropic "`) is accepted as `anthropic`.
- An empty `ANTHROPIC_API_KEY=` line counts as missing.
- Under `anthropic`, `WCL_MODEL_DISCOVERY=catalog` can't list Vertex's Model Garden; until 033 ships
  Anthropic discovery, the served set comes from probing the configured or default Claude ids
  through the Anthropic API (static discovery). A Vertex catalog is never served under `anthropic`.
- Under `anthropic`, Gemini ids in `WCL_GEMINI_MODELS`, `WCL_MODELS` or any role variable are not
  offered and not called.
- A Vertex-form dated id (`name@YYYYMMDD`) configured under `anthropic` is read as the API form
  (`name-YYYYMMDD`), and an API-form dated id under `vertex` as the Vertex form. Undated ids
  (`claude-sonnet-5-5`) are the same on both.
- An SDK error whose text could carry request headers is never echoed to the player or logged with
  the key.
- The Anthropic API rejects a turn whose replayed thinking blocks no longer match the conversation
  history (the app trims old tool results, injects a per-turn preamble and stamps the time in the
  instruction). See FR-013.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `WCL_LLM_PROVIDER` MUST accept `vertex` (default) and `anthropic`, case-insensitive
  and trimmed. Any other value MUST log one warning and use `vertex`. The value is read once per
  process; switching needs a restart.
- **FR-002**: One provider module MUST be the only code that reads the active provider and builds
  model clients (Anthropic API, Anthropic on Vertex, Gemini). Call sites MUST ask it for a client or
  a role's model and MUST NOT branch on the provider themselves.
- **FR-003**: Under `anthropic`, every Claude model the ADK agent runs (chat turns, greeting, raid
  investigation and any other `stream_response` run) MUST call the Anthropic API through the async
  Anthropic API client, never the Vertex one, through the existing retry wrapper with SDK retries
  off.
- **FR-004**: Under `vertex`, client selection, model ids, discovery and the agent MUST behave as
  today for Gemini, and Claude on Vertex MUST keep using the Vertex client at the model location.
- **FR-005**: `ANTHROPIC_API_KEY` MUST be held as a secret value that renders masked in reprs and
  settings dumps. The key MUST NOT appear in logs, WebSocket error frames, `/api/*` responses or
  exception text the app produces.
- **FR-006**: Under `anthropic` with no key (unset or empty), startup MUST log exactly one error
  naming the missing variable, MUST serve the degraded model state, and MUST NOT crash. A chat turn
  in that state MUST end with the existing friendly error frame.
- **FR-007**: The provider module MUST be the one place that tells API-form ids (dated
  `name-YYYYMMDD`, aliases) from Vertex-form ids (`name@YYYYMMDD`) and converts a configured or
  stored id into the active provider's form. No call site edits id strings itself.
- **FR-008**: Each fixed model role MUST resolve to: the explicit env value if set and servable by
  the active provider (in the active provider's id form), else the active provider's default.
  A set but unservable value (a Gemini id under `anthropic`) MUST be ignored with one warning per
  role.

  | Role | Env variable | `vertex` default (today) | `anthropic` default |
  |---|---|---|---|
  | default chat | `WCL_DEFAULT_MODEL` | `gemini-3.6-flash` | `claude-sonnet-5-5` |
  | report | `WCL_REPORT_MODEL` | `gemini-3.6-flash` | `claude-sonnet-5-5` |
  | guide (author) | `WCL_GUIDE_MODEL` | `gemini-3.7-flash` | `claude-sonnet-5-5` |
  | guide review | `WCL_GUIDE_REVIEW_MODEL` | `gemini-3.1-pro-preview` | `claude-opus-5-5` |
  | suggest / fast (suggestions, titles) | `WCL_SUGGEST_MODEL` | `gemini-3.6-flash` | `claude-haiku-5-5` |
  | greeting | `WCL_GREETING_MODEL` (new) | `gemini-3.5-flash-lite` | `claude-haiku-5-5` |

- **FR-009**: Under `anthropic`, the candidate and fallback model lists used at startup MUST hold
  only Claude ids in API form: `WCL_ANTHROPIC_MODELS` if set (converted), else the Anthropic role
  defaults' distinct ids. Gemini candidates MUST be empty, and discovery MUST run in static mode
  (probing through the Anthropic API) until 033 replaces it.
- **FR-010**: A WebSocket chat turn whose model isn't served by the active provider (after
  id-form conversion) MUST run on the active default model, with one info log line and no error
  frame. REST endpoints that take a model keep their 400 for an unserved id.
- **FR-011**: `.env.example` and README MUST document `WCL_LLM_PROVIDER`, `ANTHROPIC_API_KEY`, the
  role defaults per provider, that ADC isn't needed for LLM calls under `anthropic`, and that the key
  reaches the container through the existing `env_file: .env`. Compose MUST still start the backend
  without an ADC file.
- **FR-012**: Tests MUST use fakes or mocks only (no live LLM, no key, no ADC). They MUST cover
  client selection for both providers, the missing key, the secret-not-leaked check, the
  stale-chat-model fallback, role resolution and id-form conversion. The full backend suite MUST
  pass with no new failures against base `b963463`.
- **FR-013**: Claude agent turns MUST run on the current Claude models through ADK on both
  providers: the agent MUST give Claude an adaptive thinking configuration (today the adapter
  raises before any request is sent), and every Claude request MUST ask the API to drop thinking
  blocks invalidated by the app's per-request history edits instead of failing the turn. This
  restores Claude on Vertex. No other thinking or prompt changes.
- **FR-014**: The browser MUST NOT send a model id that `/api/models` doesn't serve: an unserved
  picker selection or reopened chat model falls back to the served default (existing behaviour,
  proven by a frontend test).

### Key Entities

- **Provider**: `vertex` or `anthropic`; one per process, read from `WCL_LLM_PROVIDER`.
- **Model role**: a named fixed use of a model (default chat, report, guide, guide review,
  suggest/fast, greeting) with one default id per provider and an optional env override.
- **Model id form**: API form (`claude-sonnet-4-20250514`, `claude-sonnet-5-5`) or Vertex form
  (`claude-sonnet-4@20250514`, `claude-sonnet-5-5`); Gemini ids have one form and run on Vertex only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Switching provider takes one `.env` line plus a restart; no other line needs editing
  for chat, greeting and the agent runs to work on the new provider.
- **SC-002**: With fakes, 100% of agent model requests under `anthropic` reach the Anthropic API
  client and 0 reach a Vertex client; under `vertex`, 0 reach the Anthropic API client.
- **SC-003**: A sentinel key value appears 0 times across all captured logs, frames, responses and
  exception text in the leak test.
- **SC-004**: With `anthropic` and no key, the backend reaches ready and serves its non-model pages;
  exactly 1 error line names the missing key.
- **SC-005**: A chat on an unserved model continues on the default with 0 error frames, and the
  browser sends 0 unserved model ids after a switch.
- **SC-006**: The backend suite has 0 new failures against base `b963463`.

## Assumptions

- Current Claude ids come from the `claude-api` skill (cached 2026-10-06): `claude-haiku-5-5`,
  `claude-sonnet-5-5`, `claude-opus-5-5`. Undated current-generation ids are the same on the Claude
  API and Vertex.
- The installed Anthropic SDK (1.11) and ADK (2.10) are kept; no dependency change. ADK's
  `AnthropicLlm` accepts a plain async Anthropic client, and `RetryingClaude` already overrides the
  client property (checked with a fake client: a full ADK turn reaches the client with all tools).
- The owner provides the key through `.env`; agents never read the owner's `.env`.
- The model picker's provider label (033) and Anthropic Models API discovery (033) are out of scope;
  under `anthropic` this feature serves the probed static Claude set.
- Non-agent call sites (suggestions, titles, reports, guides) keep calling Gemini until 035 moves
  them onto this feature's provider layer; this feature only gives them their role models.
