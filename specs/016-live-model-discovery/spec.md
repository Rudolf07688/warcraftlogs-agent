# Feature Specification: Live Model Discovery

**Feature Branch**: `016-live-model-discovery`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Please see `documentation/live_model_probe.md` for the plan for the next feature: Live Model Garden checks to fetch appropriate models."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The model picker shows current models without an operator edit (Priority: P1)

A player opens the chat and picks a model from the dropdown. Instead of a hand-maintained list that goes stale with every model release, the dropdown shows the newest models the cloud provider's model catalog offers: the latest two Gemini models of each class (pro, flash, flash-lite) and the latest Claude model of each class (haiku, sonnet, opus) that this deployment is allowed to use. When a new model version is released and enabled, it appears in the dropdown at the next refresh without anyone editing configuration.

**Why this priority**: This is the reason for the feature. Today every model release needs a configuration edit and a restart before players can choose it.

**Independent Test**: Start the app with catalog discovery on and no per-model list configured; the dropdown lists the expected newest model(s) per class, matching what the catalog lists and what answers a live call.

**Acceptance Scenarios**:

1. **Given** the catalog lists `gemini-3.8-flash`, `gemini-3.7-flash` and older flash models, all usable, **When** the app starts, **Then** the flash class in the dropdown shows exactly `gemini-3.8-flash` and `gemini-3.7-flash`.
2. **Given** the catalog lists a pro preview model newer than the newest GA pro model, **When** the app starts, **Then** the preview model is shown first and the GA model second.
3. **Given** two entries of the same version exist, one GA and one preview, **When** candidates are ordered, **Then** the GA entry ranks ahead of the preview.
4. **Given** the catalog lists experimental, text-to-speech, image, live, embedding, transcription, translation or other non-chat models, **When** the app starts, **Then** none of them appear in the dropdown.
5. **Given** the catalog lists Claude models outside the haiku/sonnet/opus classes (for example `fable` or a legacy Claude 3 model), **When** the app starts, **Then** none of them appear.
6. **Given** models appear in the dropdown, **When** a player views it, **Then** they are grouped in a stable class order: Gemini pro, flash, flash-lite, then Claude haiku, sonnet, opus.

---

### User Story 2 - Only models that actually work are offered (Priority: P1)

Being listed in the catalog does not mean this deployment can use a model. Before a model is offered, the app makes a small live call to it, including a tool declaration, because the chat agent depends on tool calls. Models that are not enabled for the project, not served in the model location, or cannot call tools are skipped, and the next-newest version of that class is tried instead. When the provider refuses a class for lack of quota, the whole class is skipped (quota applies to the class, not to one version), and the reason is recorded.

**Why this priority**: Offering a model that fails on the first chat turn is worse than not offering it. This is a precondition for User Story 1 being safe.

**Independent Test**: With a simulated catalog where the newest haiku version is not enabled, the dropdown shows the next older haiku version; with a simulated quota refusal for sonnet, no sonnet model is shown and the log says why.

**Acceptance Scenarios**:

1. **Given** the newest haiku version answers "not found / not enabled", **When** discovery runs, **Then** the next-newest haiku version that answers is shown instead.
2. **Given** a model answers a plain call but cannot handle a tool declaration, **When** discovery runs, **Then** that model is not shown.
3. **Given** a class is refused for lack of quota, and still refused after one short retry, **When** discovery runs, **Then** no other version of that class is tried, no model of that class is shown, and the startup log records "no quota" for that class.
4. **Given** the deployment currently has no Claude quota, **When** discovery runs, **Then** no Claude models are shown and the startup log states that each Claude class has no quota.
5. **Given** the Claude quota has since been granted, **When** the app is restarted with the stored discovery result cleared, **Then** haiku, sonnet and opus models appear.

---

### User Story 3 - The dropdown is never empty (Priority: P1)

If the catalog cannot be reached (network failure, permission refusal, timeout), the app falls back to the hand-maintained model lists exactly as it works today, and logs a single warning. If no model passes its live call at all, the app shows the existing "degraded" fallback list and notice. Players always have something to pick.

**Why this priority**: An empty model picker blocks every chat. This preserves the existing guarantee that model discovery never leaves the app unusable.

**Independent Test**: Start the app with the catalog unreachable; the dropdown shows the configured fallback models (probed as today, not marked degraded) and the log contains exactly one warning about the catalog.

**Acceptance Scenarios**:

1. **Given** the catalog request fails or times out, **When** the app starts, **Then** the configured fallback lists are probed as today, the result is not marked degraded, and one warning is logged.
2. **Given** the catalog is reachable but no candidate model passes its live call, **When** the app starts, **Then** the existing degraded list is served with the degraded notice.
3. **Given** the operator selects the static discovery mode, **When** the app starts, **Then** the catalog is not consulted and today's behaviour is unchanged.

---

### User Story 4 - All model calls run where current models are served (Priority: P2)

Every part of the app that calls a model (chat, class guides, reports, greeting, follow-up suggestions, discovery checks) calls it from a single configured model location that serves current Gemini and Claude models. Other regional resources keep their own region. Players never get a model in the dropdown that then fails because the chat called it from a region where it is not served.

**Why this priority**: The newest models are only served from the global location; the current regional location serves only older Gemini models and no Claude models. Without this, User Story 1 would list models that the chat then cannot reach.

**Independent Test**: With the model location set to global and the general region set to a European region, a chat turn with a tool call on the newest flash model succeeds, and guides, reports, greeting and suggestions also succeed.

**Acceptance Scenarios**:

1. **Given** the model location is global and the general region is `europe-west1`, **When** a player sends a chat turn on `gemini-3.8-flash` that triggers a tool call, **Then** the turn completes successfully.
2. **Given** the model location setting is changed, **When** any model-calling feature runs, **Then** it uses the new location; no model-calling feature keeps using the general region or a hard-coded region.

---

### User Story 5 - Restarts are fast because the discovery result is shared (Priority: P2)

Discovery takes up to one round of live calls. Its result is stored in the shared cache for six hours, so later restarts and every worker reuse it instead of probing again. A configuration change to the class settings, model location or project results in a fresh discovery rather than a stale result. If the shared cache is down, discovery still runs and the app starts normally.

**Why this priority**: Saves startup time and avoids repeated probe calls, but the feature is correct without it.

**Independent Test**: Start the app twice within six hours; the second start performs no catalog listing or probe calls and shows the same dropdown.

**Acceptance Scenarios**:

1. **Given** a discovery result was stored less than six hours ago with the same settings, **When** the app or another worker starts, **Then** it serves that result with no catalog or probe calls.
2. **Given** the class settings were changed since the result was stored, **When** the app starts, **Then** discovery runs again.
3. **Given** the cache lifetime is set to zero, **When** the app starts, **Then** discovery always runs and nothing is stored.
4. **Given** the shared cache is unreachable, **When** the app starts, **Then** discovery runs and the app starts normally.

---

### User Story 6 - Operators can see what was picked and why (Priority: P3)

At startup the operator sees one summary line (how many models, and whether they came from the catalog, the fallback lists or the degraded path) and one line per class naming the models chosen or the reason none were (for example "no quota"). The app also warns when a model used for a fixed purpose (guide writing, guide review, reports, greeting) is no longer in the catalog, so a retired model id is caught before it fails in use.

**Why this priority**: Diagnostics; useful but not required for players.

**Independent Test**: Start the app with one fixed-purpose model set to an id absent from the catalog; the log shows the per-class picks and one warning naming that setting.

**Acceptance Scenarios**:

1. **Given** discovery succeeded, **When** the startup log is read, **Then** it shows the total model count with its source and one line per configured class.
2. **Given** the guide, guide-review, report or greeting model is not listed in the catalog, **When** discovery's catalog listing succeeds, **Then** one warning per missing model is logged and that model setting is not changed.

---

### Edge Cases

- The catalog response is split over several pages: all pages are read before candidates are chosen.
- A class has fewer usable versions than its configured count: only the usable ones are shown; the class is not padded with other classes' models.
- A class has no usable version at all: it is omitted from the dropdown and the log names the reason (not enabled, no quota, or no candidates in the catalog).
- A Claude entry carries a dated version (for example `claude-haiku-4-5@20251001`) versus a default version (`claude-opus-5-5`): both produce the id the provider accepts for calls.
- Version numbers compare numerically, so `3.10` ranks above `3.9`, and `3` ranks below `3.1`.
- The configured default model did not survive discovery: the newest flash model becomes the default.
- No flash model survived either: the first model in class order becomes the default.
- A probe hangs: it is abandoned after its timeout and treated as a failure for that version.
- A transient error (not "not found", not "no quota") on a probe: treated as a failure for that version only; the next version is tried.
- A player's saved conversation references a model that is no longer offered: it is rejected as an invalid model, exactly as when the list changes today.
- The catalog lists a model the project can use but the catalog listing itself is refused (permission error): fall back to the configured lists (User Story 3).

## Requirements *(mandatory)*

### Functional Requirements

**Discovery source and selection**

- **FR-001**: The system MUST support two discovery modes, catalog and static, with catalog as the default. Static mode MUST behave exactly as model discovery does today.
- **FR-002**: In catalog mode the system MUST list the Gemini and Claude publisher catalogs at startup, reading every page, with a bounded time per request; the two listings MUST NOT wait on each other.
- **FR-003**: The system MUST classify each catalog entry into publisher, class, version and release stage, and MUST discard entries that do not match a configured class. Gemini classes are `pro`, `flash` and `flash-lite`; Claude classes are `haiku`, `sonnet` and `opus`.
- **FR-004**: The system MUST discard entries whose release stage is experimental, and MUST keep GA and public-preview entries.
- **FR-005**: Within a class the system MUST order candidates newest version first, with GA ranking ahead of preview when versions are equal.
- **FR-006**: The number of models kept per class MUST be configurable, defaulting to 2 for each Gemini class and 1 for each Claude class.
- **FR-007**: The system MUST derive the callable model id from the catalog entry, producing a bare id for default versions and an id with an `@date` suffix for dated versions.

**Live verification**

- **FR-008**: Before offering a model, the system MUST verify it with a minimal live call that includes one tool declaration; a model that fails this call MUST NOT be offered.
- **FR-009**: For each class the system MUST verify a bounded number of newest candidates (the kept count plus two) concurrently, and MUST keep the first passing candidates in version order up to the kept count.
- **FR-010**: A "not found" or "not permitted" answer MUST cause that version to be skipped and the next candidate to be considered.
- **FR-011**: A quota refusal MUST be retried once after a short pause; if it persists, the system MUST mark the whole class as "no quota" and offer no model from it.
- **FR-012**: Each verification call MUST be abandoned after a bounded timeout and counted as a failure.

**Default and presentation**

- **FR-013**: The default model MUST be the configured default if it was verified; otherwise the newest verified flash model; otherwise the first verified model in class order.
- **FR-014**: Models MUST be served in class order (Gemini pro, flash, flash-lite, then Claude haiku, sonnet, opus), newest first within a class, through the existing model-list response shape (models, default, degraded) so the player-facing interface is unchanged.

**Fallbacks**

- **FR-015**: If the catalog listing fails for any reason, the system MUST fall back to verifying the configured static lists exactly as today, MUST NOT mark the result degraded, and MUST log one warning.
- **FR-016**: If no model passes verification, the system MUST serve the existing degraded fallback list with the degraded notice. The model dropdown MUST never be empty.

**Model location**

- **FR-017**: All model calls (chat, class guides, guide review, reports, greeting, follow-up suggestions and discovery verification) MUST use a single configurable model location, defaulting to global.
- **FR-018**: The catalog MUST be listed from the global catalog, independent of the general region.
- **FR-019**: Resources other than model calls MUST keep using the general region, whose documented default becomes `europe-west1`. The hard-coded fallback region for Claude calls MUST be removed.

**Caching**

- **FR-020**: The final discovery result MUST be stored in the shared cache and reused by restarts and by all workers for a configurable lifetime defaulting to six hours; a lifetime of zero MUST disable storage.
- **FR-021**: The stored result MUST be keyed on the class settings, model location and project, so changing any of them causes a fresh discovery.
- **FR-022**: If the shared cache is unavailable, discovery MUST still run and startup MUST proceed normally.

**Diagnostics**

- **FR-023**: The startup log MUST show the number of models offered and their source (catalog, static or degraded), and one line per configured class naming the chosen models or the reason none were chosen.
- **FR-024**: After a successful catalog listing, the system MUST log one warning for each fixed-purpose model (guide, guide review, report, greeting) that is absent from the catalog, and MUST NOT change those models.

**Documentation**

- **FR-025**: The operator documentation MUST describe the new settings, why model calls use the global location, and that Claude models appear only after a Claude quota has been granted to the project.

### Key Entities

- **Catalog entry**: One model as listed by the provider's catalog: publisher, name, version identifier, release stage.
- **Model candidate**: A catalog entry that matched a configured class: publisher, class, comparable version, stage, callable model id.
- **Class setting**: A publisher class and how many models of it to keep (for example "flash: 2").
- **Verification outcome**: The result of a live call for one candidate: passed, not enabled, no quota, or failed (timeout or other error).
- **Discovery result**: What the app serves and stores: the ordered model list, the default model, the degraded flag, the source (catalog, static or degraded), the per-class outcome, and when it was produced.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A newly released, enabled model in a configured class appears in the dropdown within six hours (or at the next restart with the stored result cleared), with zero configuration edits.
- **SC-002**: 100% of models shown in the dropdown complete a chat turn that includes a tool call, with no "not found" or quota error on that first turn.
- **SC-003**: With the catalog unreachable, startup completes and the dropdown is non-empty in 100% of runs, with exactly one catalog warning in the log.
- **SC-004**: A startup that misses the stored result spends no more than about 10 seconds on verification calls beyond the catalog listing; a startup that finds a stored result spends no time on listing or verification.
- **SC-005**: On the current project, the dropdown shows exactly the expected Gemini picks (pro: `gemini-3.1-pro-preview`, `gemini-2.5-pro`; flash: `gemini-3.8-flash`, `gemini-3.7-flash`; flash-lite: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`) and the log reports "no quota" for each Claude class until Claude quota is granted.
- **SC-006**: An operator can determine, from the startup log alone, which models were chosen for every class and why any class is empty.
- **SC-007**: Chat, class guides, reports, greeting and suggestions all succeed with the model location set to global and the general region set to `europe-west1`.

## Assumptions

- The provider's catalog (Vertex Model Garden) can be listed by the project's existing credentials, and reports a release stage and version for each entry.
- Listing a model does not imply access; only a live call proves the project can use it, and quota is enforced per model class rather than per version.
- Previews are acceptable in the dropdown and can outrank older GA models, as requested. Restricting to GA only is a configuration change, not part of this feature's defaults.
- The fixed-purpose models (guide, guide review, report, greeting) stay configured by hand; this feature only warns when one is missing from the catalog.
- The existing model-list endpoint, its response shape, the stored model state and the frontend dropdown are reused unchanged.
- The hand-maintained model lists remain in configuration as the fallback for an unreachable catalog and as the source for static mode.
- The shared cache introduced in feature 014 is available for storing the discovery result, and the app already tolerates it being down.
- Requesting a Claude quota increase is an operator action in the cloud console and is outside the scope of this feature.
