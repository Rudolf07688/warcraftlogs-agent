# Feature Specification: Anthropic model discovery, provider label and discovery log fix

**Feature Branch**: `033-anthropic-discovery-label`

**Created**: 2026-10-31

**Status**: Draft

**Input**: Stories sc-250 (model discovery, catalog and busy-model fallback on the Anthropic API), sc-251 (model picker shows the live provider), sc-159 (QA SPEC-002/004: startup log line and empty-catalog handling). Builds on feature 016 (live model discovery) and feature 032 (LLM provider switch).

## Clarifications

### Session 2026-10-31

- Q1: Aliases and dated ids both count; one entry per model, the alias form wins when listed. -> FR-001, Edge Cases
- Q2: Newest = numeric version compare (3.10 > 3.9), same as Vertex.
- Q3: Reuse the Vertex retry policy. If the service's wait hint exceeds the remaining wait budget, switch to the sibling at once instead of waiting; this is logged and tested. -> FR-005
- Q4: The stored-result key gains the provider; no migration, old entries expire. -> FR-004
- Q5: Zero models in a listing is a listing failure for Vertex too (warning plus fallback list). This is a Vertex behaviour change to name in the hand-off. -> FR-009
- Q6: Provider label is a shadcn Badge shown always beside the picker. -> FR-007
- Q7: README lines are sequenced by the scrum master after 035.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The model picker lists the Claude models the Anthropic account can use (Priority: P1)

When the operator runs the app on the Anthropic API, the model picker offers the newest usable Claude models of each class (haiku, sonnet, opus), found by asking the Anthropic model catalog and checking each candidate with a small live call that includes a tool declaration. No Gemini model is offered. When a new Claude version is released and enabled for the account, it appears without anyone editing configuration.

**Why this priority**: Without it the Anthropic provider shows only a hand-maintained list that goes stale.

**Independent Test**: With a simulated Anthropic catalog (several pages, aliases and dated ids) and simulated probes, the picker lists the expected newest model per class, none of them Gemini.

**Acceptance Scenarios**:

1. **Given** the provider is the Anthropic API and the catalog lists models over several pages, **When** the app starts in catalog mode, **Then** every page is read, ids and aliases are sorted into haiku, sonnet and opus, and each class shows the newest configured number of models that answer a live tool-carrying call.
2. **Given** the newest model of a class is not enabled or has no quota, **When** discovery runs, **Then** it is skipped (a no-quota refusal skips the whole class) and the reason is logged, exactly as on Vertex.
3. **Given** static discovery mode is selected, **When** the app starts, **Then** only the configured Anthropic model list is probed, with ids in the Anthropic API form.
4. **Given** the catalog request fails, **When** the app starts in catalog mode, **Then** the static list is probed instead, one warning is logged, and the result is not marked degraded.

---

### User Story 2 - A busy Claude model falls back to its sibling (Priority: P1)

When the Anthropic API answers a turn with "too many requests" or "overloaded", the turn retries (waiting as long as the service asks), then switches to the other model of the same class. If both are busy the player sees the same friendly message as on Vertex.

**Why this priority**: Keeps chat turns from failing outright under load, matching Vertex behaviour.

**Independent Test**: Simulate 429 and 529 responses for one model: the turn completes on the sibling; with both busy the friendly message appears.

**Acceptance Scenarios**:

1. **Given** the chosen model answers 429 with a wait hint, **When** a turn runs, **Then** it retries after at least that wait, and if still busy switches to the same-class sibling.
2. **Given** both models of the class are busy, **When** a turn runs, **Then** the player sees the same friendly message as on Vertex.

---

### User Story 3 - A catalog from one provider is never served under the other (Priority: P1)

Stored discovery results are kept per provider. Switching the provider never shows the other provider's models, and any stored id that is not in the active provider's form is rejected and rediscovered.

**Why this priority**: A Vertex id served under Anthropic would fail every turn.

**Independent Test**: Store a Vertex catalog, switch to Anthropic, start: the stored one is not used and discovery runs; the reverse likewise.

**Acceptance Scenarios**:

1. **Given** a cached Vertex catalog, **When** the app starts on the Anthropic provider, **Then** the cached catalog is not served and discovery runs.
2. **Given** a cached catalog holds ids not in the active provider's form, **When** the app starts, **Then** it is discarded with a warning and rediscovered.

---

### User Story 4 - The picker shows which provider is live (Priority: P2)

The model picker carries a small read-only label, "Vertex AI" or "Anthropic API", so the player and operator can see which provider serves the models. It is readable on a 390px-wide screen and never shows a key, project id or any secret.

**Why this priority**: Diagnostics and clarity; not needed for chat to work.

**Independent Test**: Open the picker under each provider (simulated) at 390px width: the right label shows, nothing sensitive appears.

**Acceptance Scenarios**:

1. **Given** the Anthropic provider is live, **When** the picker is opened, **Then** it shows "Anthropic API".
2. **Given** the Vertex provider is live, **When** the picker is opened, **Then** it shows "Vertex AI".
3. **Given** the models endpoint is called, **Then** it also returns the provider name, and existing fields are unchanged.

---

### User Story 5 - Startup log and empty-catalog handling are correct (Priority: P3)

At startup the operator sees the model-discovery summary line specified in feature 016 (model count and source, plus one line per class). A catalog response that lists no models is treated as a failed listing, so the fallback list runs, instead of being accepted as an empty catalog. This holds for both providers.

**Why this priority**: Closes QA findings SPEC-002 and SPEC-004; diagnostics and robustness.

**Independent Test**: Simulate an empty listing under each provider: the fallback list is probed and a single warning is logged; a normal startup logs the summary line.

**Acceptance Scenarios**:

1. **Given** discovery succeeded, **When** the startup log is read, **Then** it has the summary line (count and source) and one line per class.
2. **Given** the catalog responds with zero models, **When** the app starts, **Then** it behaves as a listing failure: the fallback list is probed and one warning is logged.

---

### Edge Cases

- A class has fewer usable versions than the configured count: only usable ones are shown; the class is not padded from another.
- Aliases (undated ids such as `claude-sonnet-5-5`) and dated ids of the same model collapse to one entry in the Anthropic form.
- No model passes its live call: the existing degraded list and notice are served.
- The API key is missing: no listing or probe is attempted; the existing missing-key message applies and no secret is logged.
- A probe hangs: abandoned after its timeout, treated as a failure for that version.
- A sibling is unavailable (not configured or not enabled): the turn ends with the friendly message after the retries.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Under the Anthropic provider in catalog mode, the system MUST read all pages of the Anthropic model catalog, sort ids and aliases into the haiku, sonnet and opus classes, probe candidates with a tool-carrying one-token call, and keep the newest configured number per class that answer.
- **FR-002**: Under the Anthropic provider the system MUST NOT offer any Gemini model.
- **FR-003**: In static mode under the Anthropic provider the system MUST probe the configured model list in Anthropic API id form, and MUST use it as the fallback when listing fails.
- **FR-004**: The stored discovery result MUST be keyed by provider, MUST never be served under the other provider, and its ids MUST be validated in the active provider's id form before use.
- **FR-005**: On a "too many requests" or "overloaded" answer from the Anthropic API, the system MUST retry honouring the service's wait hint, then switch to the same-class sibling, and when both are busy show the same friendly message as on Vertex.
- **FR-006**: The models endpoint MUST return the active provider name as an additional field without changing existing fields.
- **FR-007**: The model picker MUST show a read-only provider label ("Vertex AI" or "Anthropic API"), readable at 390px, and MUST NOT display any key, project id or secret.
- **FR-008**: The system MUST emit the model-discovery startup log line(s) specified in feature 016 (count and source, one line per class) under both providers.
- **FR-009**: A catalog response with no models MUST be treated as a listing failure (fallback runs, one warning), not as an empty catalog, under both providers.
- **FR-010**: Vertex behaviour MUST otherwise be unchanged and its existing discovery tests MUST pass.
- **FR-011**: The system MUST NOT write the API key to logs, responses or errors.

### Key Entities

- **Model catalog**: the list of offered models, their class, source (catalog, fallback, degraded) and provider; stored per provider.
- **Model class**: haiku, sonnet or opus (Anthropic); pro, flash, flash-lite plus Claude classes (Vertex).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the Anthropic provider and a simulated catalog, 100% of offered models are Claude models, and the newest usable models of each class are shown.
- **SC-002**: A second start within the storage lifetime performs no listing or probe calls, and switching provider never shows the other provider's models (0 cross-provider hits in tests).
- **SC-003**: Under simulated busy responses for one model, 100% of turns complete on the sibling; with both busy, the friendly message appears.
- **SC-004**: The provider label is visible and fully readable at 390px width in both provider states, and no secret appears in the page or the endpoint response.
- **SC-005**: An empty listing triggers the fallback in 100% of simulated cases for both providers, and every start logs the summary line.

## Assumptions

- Feature 032's provider layer is the only place that reads the provider setting; this feature adds listing there.
- The existing class, count and static-list settings from 016/032 are reused; no new required settings.
- Live checks against the real Anthropic API are outside this feature's tests (fakes only).
- The friendly "busy" message and the retry-then-sibling flow from the Vertex path are reused unchanged.
