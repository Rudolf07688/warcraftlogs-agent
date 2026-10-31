# Feature Specification: Suggestions, titles, reports and class guides on the active LLM provider

**Feature Branch**: `035-provider-generation-callsites`

**Created**: 2026-10-31

**Status**: Signed off (scrum master, 2026-10-31)

**Stories**: sc-252 (2) follow-up suggestions, chat titles and report synthesis run on the active
LLM provider · sc-253 (3) grounded class-guide pipeline runs on the Anthropic API (structured
output and web search). Epic 248 (switchable LLM provider).

**Input**: User description: "Feature 035: follow-up suggestions, chat titles, PDF report
synthesis and the grounded class-guide pipeline run on the active LLM provider
(`WCL_LLM_PROVIDER=vertex|anthropic`, from feature 032's provider layer). One provider-neutral
text-generation entry point in a new `wcl_agent/llm/generation.py` (the only module besides
`provider.py` that may call `active_provider()`) serves suggestions, titles and reports through
the shared rate-limit retry loop; guide structured output and search-grounded research run on
Claude via the Anthropic API (JSON-schema structured output, server-side web search, web fetch
for URL context restricted by `WCL_GUIDE_RESEARCH_FETCH_ENABLED`). Vertex behaviour unchanged;
fail-closed behaviour and timeouts unchanged; tests with fakes only."

**Prior context (cited, not re-derived):** sprint plan `sprints/2026-10-31/plan.md` section 035
and decisions D1–D5, D9, D10; provider-layer contract
`sprints/2026-10-31/briefs/032-provider-layer-contract.md` (authoritative copy after 032 merges:
`specs/032-llm-provider-switch/contracts/provider-layer.md`); suggestions fail fast
(`specs/011-agent-rate-limit-relief`, FR-012); titles (`specs/019-sidebar-conversations`, FR-017);
report synthesis fail-closed (`specs/007-metadata-reports-profiles`, FR-017/018/019); guide
pipeline (`specs/015-grounded-class-guides`, FR-046 reviewer differs, research R3/R14).

## Clarifications

### Session 2026-10-31

Answered by the scrum master (spec signed off 2026-10-31).

- Q: How does the entry point pick the client? → A: By model family (`is_anthropic_model`): a
  Claude id goes to the active provider's Claude client (Anthropic API under `anthropic`,
  Vertex Model Garden under `vertex`), a Gemini id to the genai client. `generation.py` calls
  `active_provider()` only to choose server-tool variants (Claude on Vertex has only basic web
  search and no web fetch).
- Q: How are thinking-off calls (suggestions, titles) sent to Claude? → A: Haiku ids get thinking
  disabled; any other Claude id gets no thinking setting and the lowest effort. A refusal of that
  request (400) fails closed like any other error. One fake-client test per branch asserts the
  request shape.
- Q: Which retry policy does each sc-252 call site use through the shared loop? → A: Reports one
  attempt (as today), suggestions one attempt (011 FR-012), titles keep their two attempts.
- Q: A Claude research turn where searches ran but every one returned an error and none returned
  results? → A: Raise the pipeline's model error (run held). A turn with no searches, or with
  successful but empty searches, continues as today. Gemini unchanged.
- Q: How does the grounded call learn the allowed fetch domains? → A: `generate_grounded` takes a
  `fetch_domains` argument; `research.py` passes `fetchable_domains()` (one-line change, research
  joins the footprint). Gemini keeps URL context as today.
- Also decided: web search and web fetch use the dynamic-filtering tool versions on the Anthropic
  API, at most 10 searches and 5 fetches per research call; a paused server turn is resumed at
  most 3 times; structured output asks for a JSON schema built from the Pydantic model and is
  validated by our own schema check (one-retry rule unchanged); temperature is never sent to
  Claude; existing tests that patched removed internals move to the new seam with the same
  assertions.
- Also decided: this feature owns the sprint-level end-to-end test: one new parametrised test file
  covering the agent (with 032's fakes), suggestions, titles, report synthesis and the guide
  pipeline (`anthropic` reaches only the faked Anthropic client, `vertex` only Vertex clients), plus
  the plan's grep check (outside `provider.py` and `generation.py`, no direct genai/anthropic
  client imports for model calls; ADK agent types excepted).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Suggestions and chat titles keep working after a switch (Priority: P1) · sc-252

The owner sets `WCL_LLM_PROVIDER=anthropic` and restarts. A player asks Barnaby about last night's
raid. When the answer is done, up to three follow-up questions appear under it, and the new chat
in the sidebar gets a short generated title, just as on Vertex. Both now come from the fast Claude
model on the Anthropic API. If that model is slow, rate-limited or down, the answer still stands:
there are simply no suggestions, and the chat keeps its first-message title.

**Why this priority**: These run after every first answer. Under `anthropic` today they call
Gemini, which either fails (no Google credentials) or bills Vertex behind the owner's back (D2).

**Independent Test**: With a faked Anthropic client and `WCL_LLM_PROVIDER=anthropic`, finish a
turn and check that suggestions and the title come from the fake on the fast-role model, and that
nothing reaches the genai client. Repeat with `vertex` and a faked genai client.

**Acceptance Scenarios**:

1. **Given** `anthropic`, **When** a turn finishes, **Then** follow-up suggestions are generated
   by the fast-role model (default `claude-haiku-5-5`) on the Anthropic API and parsed by the
   same rules as today (at most 3, de-duplicated, trivial replies give none).
2. **Given** `anthropic`, **When** a chat's first reply completes, **Then** its title is
   generated by the fast-role model and cleaned by the same rules as today.
3. **Given** either provider, **When** the suggestion call fails, is rate-limited or exceeds its
   4-second bound, **Then** the turn has no suggestions, nothing is retried, and the turn is not
   affected.
4. **Given** either provider, **When** the title call fails or exceeds its 15-second bound
   (one rate-limit retry allowed, as today), **Then** the chat keeps its first-message title and
   no second attempt is made.
5. **Given** `vertex` (or the setting absent), **When** suggestions and titles run, **Then** they
   use the same Gemini fast model and thinking-off settings as today.

---

### User Story 2 - PDF findings reports keep working after a switch (Priority: P1) · sc-252

A player exports a chat (or one answer) as a PDF findings report. Under `anthropic` the findings
are written by the report-role Claude model (default `claude-sonnet-5-5`) on the Anthropic API.
If the model fails or takes longer than the report bound, the player gets the same clean error as
today and never a half-written PDF.

**Why this priority**: Reports are a user-visible export; under `anthropic` they would otherwise
fail or silently use Vertex.

**Independent Test**: With a faked Anthropic client, request a conversation report and a message
report under `anthropic`; check the findings Markdown comes from the fake on the report-role model.
Make the fake raise or hang and check the clean 500 with no file.

**Acceptance Scenarios**:

1. **Given** `anthropic`, **When** a report is requested, **Then** the findings document is
   generated by the report-role model with the same prompt and output cap as today.
2. **Given** either provider, **When** the model errors, returns nothing, or exceeds the
   60-second bound, **Then** the request ends in the existing clean 500 and no partial file.
3. **Given** either provider, **When** a report is generated, **Then** the model call no longer
   occupies a worker thread while it waits.
4. **Given** `vertex`, **When** a report is requested, **Then** the same Gemini report model and
   settings are used as today.

---

### User Story 3 - Class guides are authored and reviewed on Claude (Priority: P1) · sc-253

A guide run starts (scheduled, stale-guide scan, or a player's inaccuracy report). Under
`anthropic`, the author step and the reviewer step each ask Claude for a typed JSON reply, which
is checked against the same schema as today. A reply that does not fit is retried once; a second
misfit, or any model error, holds the run exactly as today. The author and the reviewer are two
different Claude models by default (author `claude-sonnet-5-5`, reviewer `claude-opus-5-5`), and
the startup warning still fires if someone sets them to the same model.

**Why this priority**: Guides are a core feature; without this they cannot be generated at all
under `anthropic`.

**Independent Test**: With a faked Anthropic client returning a misfit JSON reply and then a
valid one, run the author step and check one retry and a validated result; with two misfits,
check the run is held with a model error.

**Acceptance Scenarios**:

1. **Given** `anthropic`, **When** a structured guide call runs, **Then** Claude is asked for JSON
   matching the step's schema and the reply is validated against that same schema.
2. **Given** a reply that fails validation, **When** the call runs, **Then** it is retried once;
   a second failure raises the pipeline's model error and the run is held (unchanged behaviour).
3. **Given** `anthropic` with no role overrides, **When** the app starts, **Then** the guide
   author and reviewer models differ, and the existing "reviewer equals author" startup warning
   still runs when an operator configures them equal.
4. **Given** `vertex`, **When** a structured guide call runs, **Then** it uses Gemini's JSON
   schema mode exactly as today.

---

### User Story 4 - Guide research stays grounded and cited on Claude (Priority: P2) · sc-253

The research step collects current facts for a spec from the web. Under `anthropic`, Claude runs
Anthropic's server-side web search, and may open pages only on the domains the fetch rules allow
(official Blizzard sites always; third-party guide sites only when
`WCL_GUIDE_RESEARCH_FETCH_ENABLED` is on). The research notes come back with the `{title, uri}`
of every search and fetch result, so the extraction step and the guide's citations work as on
Vertex. If the owner has not enabled web search for the Anthropic organisation, the research step
fails with a clear model error naming the fix, and the run is held; the README says how to enable
it.

**Why this priority**: Without grounding a guide cannot be cited. It depends on User Story 3's
structured extraction to be useful end to end.

**Independent Test**: With a faked Anthropic client returning web-search and web-fetch result
blocks, run the research collection and check the text and the deduplicated `{title, uri}`
sources; check the fetch domains sent match the fetch rules for both settings of the flag; fake
the "web search is not enabled" refusal and check the clear model error.

**Acceptance Scenarios**:

1. **Given** `anthropic`, **When** the research collection runs, **Then** the request carries the
   server-side web search tool and the reply's text and `{title, uri}` sources (from the search
   and fetch result blocks, de-duplicated by URI, in order) come back in the same grounded-text
   shape as today.
2. **Given** `anthropic`, **When** URL context is requested, **Then** it maps to the server-side
   web fetch tool restricted to the allowed fetch domains; with
   `WCL_GUIDE_RESEARCH_FETCH_ENABLED` off only the official domains are allowed, and no request
   ever allows a domain the rules forbid.
3. **Given** the server pauses a long search turn, **When** research runs, **Then** the turn is
   resumed (bounded) and the final text and all sources are returned.
4. **Given** web search is disabled for the Anthropic organisation, **When** research runs,
   **Then** it raises the pipeline's model error with a message that web search must be enabled
   in the Anthropic Console, and the run is held as today.
5. **Given** `vertex`, **When** research runs, **Then** it uses Google Search and URL context and
   reads grounding metadata exactly as today.

---

### Edge Cases

- A Gemini id set explicitly for a role under `anthropic` (e.g. the owner's old
  `WCL_SUGGEST_MODEL=gemini-3.6-flash`): the provider layer already replaces it with the Claude
  role default (032, D9 FYI-1); call sites never see the Gemini id.
- `anthropic` without `ANTHROPIC_API_KEY`: the provider layer refuses to build the client
  (`LlmProviderNotConfigured`, key-free message). Suggestions give none, titles stay, reports
  return the clean 500, guide runs are held. No secret appears in any error or log.
- A `temperature` passed by a call site under Claude: accepted and not sent (current Claude models
  reject non-default sampling values).
- A Claude reply that stops at the token cap: the text is used as is (suggestions and titles parse
  what they get; a truncated structured reply fails validation and is retried once).
- Every web search in a Claude research turn returns an error block (rate limit, unavailable) and
  none returns results: the pipeline's model error, run held. No searches at all, or successful
  but empty searches: the turn continues with no sources, as on Gemini.
- A Claude reply refused for safety reasons (`refusal` stop reason): treated as a failed call
  (no suggestions / title kept / clean 500 / model error).
- Sources whose URL is a Vertex grounding redirect keep being resolved as today; Anthropic sources
  are already final URLs and pass through unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST offer one provider-neutral text-generation entry point taking a
  prompt, a model role, a maximum output size, an optional temperature and a retry policy, that
  generates text on whichever provider serves the role's model, through the shared rate-limit
  retry loop.
- **FR-002**: Follow-up suggestions, chat titles and report synthesis MUST use that entry point.
  Those three modules MUST NOT import provider SDK types or branch on the provider.
- **FR-003**: Suggestions and titles MUST use the fast role's model; report synthesis MUST use the
  report role's model, as resolved by the provider layer (no fixed model ids left in these call
  sites).
- **FR-004**: Suggestions MUST keep failing fast (no retry on a rate limit, FR-012 of 011), within
  4 seconds, and return no suggestions on any failure.
- **FR-005**: Titles MUST keep their single rate-limit retry and 15-second bound and keep the
  first-message title on any failure.
- **FR-006**: Report synthesis MUST keep its 60-second bound, output cap, input cap and fail-closed
  result (clean 500, no partial file), and MUST NOT block a worker thread while waiting.
- **FR-007**: Under Claude, the entry point MUST NOT send temperature or other sampling values,
  and MUST NOT force a tool choice. Calls that are thinking-off on Gemini MUST send thinking
  disabled to Haiku ids and, for any other Claude id, no thinking setting and the lowest effort.
- **FR-008**: The guide pipeline's structured call MUST work on both providers: on Claude it asks
  for JSON matching the step's schema; on both, the reply is validated against that same schema
  with one retry on a misfit, then the pipeline's model error.
- **FR-009**: The guide pipeline's grounded call MUST work on both providers: on Claude it uses the
  server-side web search tool and returns the text plus `{title, uri}` sources taken from the
  search (and fetch) result blocks, de-duplicated by URI. On Claude, a turn where at least one
  search returned an error and none returned results MUST raise the pipeline's model error.
- **FR-010**: On Claude, URL context MUST map to the server-side web fetch tool, restricted to the
  domains the fetch rules allow (`WCL_GUIDE_RESEARCH_FETCH_ENABLED`); where web fetch is not
  available, URL context MUST be omitted and the README MUST say so.
- **FR-011**: A refusal because web search (or web fetch) is not enabled for the Anthropic
  organisation MUST surface as the pipeline's model error with a message naming the Console fix;
  the run is held as today. README MUST say how to enable web search.
- **FR-012**: Under `anthropic`, guide author and reviewer MUST default to two different Claude
  models (032's role defaults); the existing startup check that they differ MUST still run.
- **FR-013**: `vertex` behaviour MUST be unchanged for all four call sites: same Gemini models,
  same request settings, same parsing, same timeouts and retry rules.
- **FR-014**: Only the provider layer (`provider.py` and the new `generation.py`) may decide which
  client to call. The call sites MUST NOT call `active_provider()` or construct clients; the
  transitional `vertex.genai_client` forwarder MUST no longer be used by these call sites.
- **FR-015**: Clients MUST be created once per process and reused (PERF-005), with the SDK's own
  retries off where the shared retry loop owns retries.
- **FR-016**: Tests MUST use faked Anthropic and genai clients only (including web-search and
  web-fetch result blocks, a paused turn, the "not enabled" refusal and a validation retry); no
  live calls. The existing suggestion, title, report and guide-pipeline tests MUST still pass,
  moved to the new seam where they patched removed internals.
- **FR-017**: Each sc-252 call site MUST pass its retry policy to the entry point: suggestions and
  reports one attempt, titles two attempts (their existing policy).

### Key Entities

- **Model role**: the job a model does (fast, report, guide author, guide reviewer), from 032's
  provider layer; each role resolves to one served model id per provider.
- **Grounded text**: research notes plus the ordered, de-duplicated list of `{title, uri}` sources
  the search and fetch tools returned (unchanged shape).
- **Fetch domains**: the domains research may open, from the existing source tiers and the
  third-party fetch flag (unchanged rules).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With `anthropic` and fakes, suggestions, titles, report synthesis and every guide
  pipeline call reach the faked Anthropic client and none reaches genai; with `vertex`, none
  reaches the Anthropic client (one parametrised test).
- **SC-002**: Outside the provider layer, no module among the four call sites imports a provider
  SDK client or type, or reads the provider setting (grep check).
- **SC-003**: 100% of the existing suggestion, title, report and guide-pipeline tests pass.
- **SC-004**: Suggestions still give up within 4 s, titles within 15 s and reports within 60 s on a
  hung model, on both providers (tests with hanging fakes).
- **SC-005**: A research run under `anthropic` whose organisation has web search disabled is held
  with a message that names the Console setting, in 100% of runs (no crash, no partial guide).
- **SC-006**: Live (owner, Under Review): one PDF report and one class guide on each provider;
  suggestions and a title appear under `anthropic`.

## Assumptions

- 032 (provider layer, role resolution, `settings.wcl_*_model` resolved per provider) merges before
  implementation starts; this feature calls it and does not change it (`provider.py`, `config.py`,
  `main.py`, `model_retry.py` are not edited).
- Under `anthropic` only Claude ids are served (032), so model-family dispatch (Clarifications)
  sends every call there to the Anthropic API.
- Chat web search under Claude stays out of scope (D3).
- The owner enables Anthropic web search in the Console before the live guide check; searches are
  billed per use, so a request caps the number of searches.
- The sprint-level end-to-end parametrised test and grep check (plan "End-to-end acceptance") are
  this feature's (Clarifications); the agent part reuses 032's fakes.
