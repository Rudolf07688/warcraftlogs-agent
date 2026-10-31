---

description: "Tasks for 035: suggestions, titles, reports and class guides on the active LLM provider"
---

# Tasks: Suggestions, titles, reports and class guides on the active LLM provider

**Input**: `specs/035-provider-generation-callsites/` (spec signed off, plan, research R1–R8,
contracts/generation.md, data-model.md, quickstart.md)

**Prerequisites**: 032 merged into `sprint-2026-10-31` and this branch rebased on it (scrum master
says "032 MERGED, rebase"). Nothing below starts before that.

**Tests**: Required (AC 6, FR-016). Fakes only: Claude via the real `AsyncAnthropic` over an
`httpx2.MockTransport` returning scripted Messages API JSON (R7); genai via object fakes of
`client.aio.models.generate_content`.

**Rules for every task**: GitNexus `impact` (upstream) before editing a symbol; no edits to
`provider.py`, `config.py`, `main.py`, `model_retry.py`; never send `temperature`/`top_p`/`top_k`
or a forced `tool_choice` to Claude; restore `CLAUDE.md` and `.specify/feature.json` before every
commit; never push.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 suggestions + titles, US2 reports, US3 structured guide calls, US4 grounded
  research (spec user stories)

---

## Phase 1: Setup

- [ ] T001 Rebase `035-provider-generation-callsites` on `sprint-2026-10-31` after 032 merges; run
  `uv run --extra test pytest -q` to record the green baseline; re-index the worktree
  (`node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force`); confirm
  `provider.ModelRole`, `role_model`, `async_anthropic_client`, `genai_client`, `active_provider`
  match `specs/032-llm-provider-switch/contracts/provider-layer.md` and note any drift in
  `specs/035-provider-generation-callsites/checkpoint.md`.

---

## Phase 2: Foundational (blocks all stories)

- [ ] T002 Create `wcl_agent/llm/generation.py` skeleton per `contracts/generation.md`: module
  docstring (part of the provider layer; only it and `provider.py` call `active_provider()`),
  `functools.cache`d `_claude_client()` → `provider.async_anthropic_client(max_retries=0)` and
  `_genai_client()` → `provider.genai_client()`, `ModelRefused`, `ServerToolDisabled`, the
  `Grounded` dataclass, and the private `_claude_text(response)` helper (join `text` blocks; raise
  `ModelRefused` on `stop_reason == "refusal"`).
- [ ] T003 Create the shared fakes in `backend/tests/test_llm_generation.py`: a `scripted_claude`
  fixture (MockTransport answering each request with the next scripted Messages JSON or an error
  status, recording request bodies; installs a real `AsyncAnthropic` via
  `monkeypatch.setattr(generation, "_claude_client", ...)`), a `fake_genai` fixture (records
  `model`/`contents`/`config`, returns or raises scripted items), a `use_provider` fixture
  (env + `active_provider.cache_clear()` + `generation` cache clears), and message builders
  (`text_message`, `search_result_block`, `search_error_block`, `fetch_result_block`,
  `paused_message`).

**Checkpoint**: module imports; fixtures usable by the story tests.

---

## Phase 3: User Story 1 - Suggestions and titles on the active provider (P1, sc-252)

**Goal**: suggestions and titles run through `generate_text` on the fast role, on either provider.

**Independent test**: under `anthropic`, a finished turn's suggestions and title come from the
scripted Claude transport on `claude-haiku-5-5`; under `vertex`, from the genai fake on the Gemini
fast model with thinking budget 0; nothing reaches the other client.

- [ ] T004 [US1] Implement `generate_text` in `wcl_agent/llm/generation.py` (R2): model
  `provider.role_model(role)`; one call per attempt inside
  `model_retry.generate_with_retry(..., policy)`; Gemini `GenerateContentConfig(max_output_tokens,
  temperature, thinking_config=ThinkingConfig(thinking_budget=0) if not thinking)` (omit unset
  fields so each call site's config equals today's); Claude `messages.create(model, max_tokens,
  messages=[{"role": "user", "content": prompt}])` plus, when `thinking=False`,
  `thinking={"type": "disabled"}` for `claude-haiku-*` ids else `output_config={"effort": "low"}`;
  never `temperature`.
- [ ] T005 [US1] Tests for `generate_text` in `backend/tests/test_llm_generation.py`: role → model
  per provider; Claude body has no `temperature` and the Haiku vs non-Haiku thinking-off shapes
  (clarify Q2, one test per branch); Gemini config fields; a 429 retried once under a 2-attempt
  policy and not retried under attempts=1; refusal raises `ModelRefused`; text blocks joined.
- [ ] T006 [US1] Switch `backend/app/suggestions.py` to `generate_text(prompt, ModelRole.FAST,
  max_tokens=_MAX_OUTPUT_TOKENS, policy=RetryPolicy(attempts=1), thinking=False)` inside the
  existing `asyncio.wait_for(SUGGEST_TIMEOUT_S)`; remove `_SUGGEST_MODEL`, `_client`, `_get_client`
  and the `google.genai`/`os` imports; keep `parse_followups` and the fail-closed `except`; update
  the docstrings (fast role, either provider, FR-012 still holds).
- [ ] T007 [US1] Switch `backend/app/services/conversation_titles.py` `generate_title` to
  `generate_text(prompt, ModelRole.FAST, max_tokens=_MAX_OUTPUT_TOKENS, policy=_POLICY,
  temperature=0.2, thinking=False)`; drop the `suggestions` import, the inner generator and the
  `google.genai` import; `retitle_conversation` unchanged.
- [ ] T008 [US1] Move `backend/tests/test_suggestions.py` patches of `suggestions._client` /
  `_SUGGEST_MODEL` to the `generation` seam (genai fake via `generation._genai_client`; model
  asserted as the FAST role model); keep every assertion (one attempt on 429 and no sleep; thinking
  budget 0; timeout → []); add one `anthropic` test (scripted Claude → parsed suggestions, model
  `claude-haiku-5-5`, genai fake untouched).
- [ ] T009 [US1] Move `backend/tests/test_conversation_titles.py` `_fake_client` from
  `suggestions._get_client` to the `generation` seam with the same assertions (cheap model,
  thinking budget 0, prompt content, one retry then `ModelRateLimited`); add one `anthropic` test
  (title from scripted Claude on the FAST model, body without `temperature`).
- [ ] T010 [US1] Run `uv run --extra test pytest -q backend/tests/test_llm_generation.py
  backend/tests/test_suggestions.py backend/tests/test_conversation_titles.py`; green.

**Checkpoint**: US1 complete and green.

---

## Phase 4: User Story 2 - PDF findings reports on the active provider (P1, sc-252)

**Goal**: report synthesis runs through `generate_text` on the report role, async, fail-closed.

**Independent test**: under `anthropic`, `synthesize_findings` returns the scripted Claude text
on `claude-sonnet-5-5` with `max_tokens=16384`; a hanging fake ends in `TimeoutError` within the
bound; under `vertex`, the genai fake sees `max_output_tokens=16384` and no thread is used.

- [ ] T011 [US2] Switch `backend/app/services/report_synthesis.py`: remove `_generate` and the
  thread; `synthesize_findings` awaits `asyncio.wait_for(generate_text(prompt, ModelRole.REPORT,
  max_tokens=_MAX_OUTPUT_TOKENS, policy=_POLICY), _TIMEOUT_S)` with `_POLICY =
  RetryPolicy(attempts=1)` and returns the stripped text; drop the `settings` import if unused;
  update the module docstring (async client, either provider).
- [ ] T012 [US2] Move `backend/tests/test_report_synthesis.py` from `rs._generate` to an async
  fake of `rs.generate_text` (happy path, empty → "", exception propagates, timeout with an
  `asyncio.sleep` fake, output cap asserted as `max_tokens == rs._MAX_OUTPUT_TOKENS` and role
  `REPORT`); add one `anthropic` test through the scripted transport; run the file plus
  `backend/tests/test_reports.py backend/tests/test_pdf_report.py backend/tests/test_message_report.py`.

**Checkpoint**: US1 + US2 complete (sc-252 done).

---

## Phase 5: User Story 3 - Structured guide calls on Claude (P1, sc-253)

**Goal**: `generate_structured` works on both providers with the same validation and retry rule.

**Independent test**: scripted Claude returns a misfit JSON then a valid one → one retry and a
validated model; two misfits → `GuideModelError`; under `vertex` the genai config still carries
`response_mime_type="application/json"`, `response_schema=schema`, `temperature`.

- [ ] T013 [US3] Implement `generate_json` in `wcl_agent/llm/generation.py` (R3): Gemini
  `GenerateContentConfig(temperature, response_mime_type="application/json",
  response_schema=schema)`; Claude `output_config={"format": {"type": "json_schema", "schema":
  anthropic.transform_schema(schema)}}`, `max_tokens=16_000`; both under `generate_with_retry`;
  returns the raw text.
- [ ] T014 [US3] Change `backend/app/services/guide_pipeline/llm.py` `generate_structured` to call
  `generation.generate_json(model, prompt, schema, policy=_policy(), temperature=temperature)`;
  keep the 2-iteration validation loop, the error wrapping and `GuideModelError`; remove `_client`,
  `_get_client` and `_generate` once `generate_grounded` (T018) no longer needs them; update the
  module docstring (provider-neutral via `generation`).
- [ ] T015 [US3] Tests in `backend/tests/test_guide_pipeline_llm.py` (new): both providers ×
  (valid first reply; misfit then valid → 2 calls; two misfits → `GuideModelError`; SDK error →
  `GuideModelError`); Claude body has `output_config.format.type == "json_schema"`, no
  `temperature`, no `tool_choice`; Gemini config unchanged; under `anthropic` with no overrides
  `role_model(GUIDE) != role_model(GUIDE_REVIEW)` (AC 5); run with
  `backend/tests/test_guide_pipeline_review.py backend/tests/test_guide_pipeline_run.py`.

**Checkpoint**: US3 green; authoring and review run on Claude.

---

## Phase 6: User Story 4 - Grounded research on Claude (P2, sc-253)

**Goal**: research runs Anthropic web search (+ restricted web fetch), returns `{title, uri}`
sources, and fails clearly when the tool is disabled or every search failed.

**Independent test**: scripted Claude with search + fetch result blocks and one `pause_turn` →
text and de-duplicated sources; `allowed_domains` equals `fetchable_domains()` with the fetch flag
off and on; the "not enabled" 400 → `GuideModelError` naming the Console page; error blocks only
→ `GuideModelError`.

- [ ] T016 [US4] Implement `generate_grounded` in `wcl_agent/llm/generation.py` (R4–R6): Gemini
  path = today's `google_search` (+ `url_context` iff `fetch_domains`) with automatic function
  calling disabled and `temperature=0.2`, sources via the moved `grounding_sources`; Claude path =
  tools per `active_provider()` (`anthropic`: `web_search_20260209` max_uses 10 +
  `web_fetch_20260209` max_uses 5 `allowed_domains=list(fetch_domains)` when non-empty; `vertex`:
  `web_search_20250305` only), `max_tokens=16_000`, `pause_turn` resumed ≤3 times by re-sending
  `[user, assistant(content)]`, blocks collected across responses → text, sources (search results
  then fetch results, de-duplicated by URL) and `search_errors`; an `anthropic.BadRequestError`
  whose message says web search/fetch "is not enabled" → `ServerToolDisabled` naming
  https://platform.claude.com/settings/capabilities.
- [ ] T017 [US4] Change `backend/app/services/guide_pipeline/research.py`
  `collect_evidence_basic` to call `llm.generate_grounded(settings.wcl_guide_model, collect,
  fetch_domains=fetchable_domains())`.
- [ ] T018 [US4] Change `backend/app/services/guide_pipeline/llm.py` `generate_grounded(model,
  prompt, *, fetch_domains)` to call `generation.generate_grounded(..., policy=_policy())`, wrap
  errors in `GuideModelError` as today, raise `GuideModelError("web search failed: <codes>")` when
  `search_errors` and no sources (clarify Q4), raise on empty text as today, return
  `GroundedText(text, sources)`; delete the local `grounding_sources` and the now-unused client
  helpers; no `google.genai` import left in the module.
- [ ] T019 [US4] Update the fake signatures `*, url_context` → `*, fetch_domains` in
  `backend/tests/test_guide_pipeline_run.py` and `backend/tests/test_guide_reports.py` (signature
  and the recorded tuple only).
- [ ] T020 [US4] Grounded tests in `backend/tests/test_guide_pipeline_llm.py`: Claude search +
  fetch blocks + a duplicate URL → sources in order without duplicates; one `pause_turn` then
  `end_turn` → 2 requests, second carries the paused assistant content unchanged, text from both;
  `allowed_domains` with `WCL_GUIDE_RESEARCH_FETCH_ENABLED` off (official only) and on, via
  `research.collect_evidence_basic` with `llm.generate_structured` stubbed; empty `fetch_domains` →
  no web fetch tool; Vertex-Claude → `web_search_20250305` and no fetch; "not enabled" 400 →
  `GuideModelError` with the Console URL; only error blocks → `GuideModelError`; no searches or
  empty successful search → continues; Gemini path unchanged (tools, config, sources from
  grounding metadata).
- [ ] T021 [US4] Run `uv run --extra test pytest -q backend/tests/test_guide_pipeline_llm.py
  backend/tests/test_guide_pipeline_research.py backend/tests/test_guide_pipeline_run.py
  backend/tests/test_guide_reports.py backend/tests/test_guide.py`; green.

**Checkpoint**: sc-253 complete.

---

## Phase 7: Polish and cross-cutting

- [ ] T022 Create `backend/tests/test_provider_e2e.py` (sprint-level e2e, clarify): parametrised
  over `vertex`/`anthropic`, the agent turn (032's scripted transport technique), suggestions,
  title, report synthesis, `generate_structured` and `generate_grounded` reach only the faked
  Anthropic client under `anthropic` and only the genai fake / Vertex Claude client under `vertex`;
  plus the grep check: outside `wcl_agent/llm/provider.py` and `wcl_agent/llm/generation.py`, no
  module in `backend/app/` or `wcl_agent/` imports `google.genai` client types or `anthropic`
  clients for model calls (ADK agent types and `model_retry`'s error classification excepted,
  allow-list kept explicit in the test), and nothing outside those two calls `active_provider()`.
- [ ] T023 README lines in 032's provider section of `README.md`: suggestions, titles, reports and
  guides follow `WCL_LLM_PROVIDER`; guides need web search (and web fetch) enabled at Anthropic
  Console → Settings → Capabilities (billed per search; a held run says so); URL context is not
  available for Claude on Vertex.
- [ ] T024 If 033 has merged and `wcl_agent/llm/models.py` no longer calls
  `vertex.genai_client`, delete that forwarder from `wcl_agent/llm/vertex.py` (text search for
  callers first); otherwise record in `checkpoint.md` that 033 deletes it.
- [ ] T025 Full suite `uv run --extra test pytest -q`; GitNexus `analyze --index-only` +
  `detect-changes --scope all --repo .` (re-run on partial/truncated); ownership check
  `git diff --name-only sprint-2026-10-31...HEAD`; restore `CLAUDE.md` and
  `.specify/feature.json`; hand-off message to the scrum master.

---

## Dependencies & Execution Order

- T001 → T002 → T003 → stories.
- US1 (T004–T010) first: `generate_text` is shared with US2.
- US2 (T011–T012) after T004.
- US3 (T013–T015) after T002/T003; independent of US1/US2.
- US4 (T016–T021) after US3 (T014 and T018 edit the same `llm.py`; T018 removes helpers T014
  keeps).
- T022 after all stories; T023/T024 any time after T001; T025 last.

## Parallel opportunities

All story tasks edit `generation.py` or the shared `llm.py`, so the work is sequential for one
developer; [P] is not used. No sub-agents proposed (one module plus small call-site edits;
splitting would cost more review than it saves).

## Implementation strategy

MVP = US1 (the entry point and the two most frequent calls). Then US2 (finishes sc-252), US3,
US4 (finishes sc-253), then the e2e/grep test and README. Commit after each story checkpoint
(green tests).
