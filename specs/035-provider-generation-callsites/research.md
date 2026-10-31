# Research: 035 provider generation call sites

All decisions below follow the signed-off spec (Clarifications 2026-10-31), the 032 provider
contract and the `claude-api` skill (checked against the live web search / web fetch docs on
2026-10-31 and the installed SDK, `anthropic` 1.11.0, `google-genai` 2.25.0).

## R1. Where the provider decision lives

- **Decision**: New `wcl_agent/llm/generation.py`. It picks the client by model family
  (`model_retry.is_anthropic_model`): Claude ids use `provider.async_anthropic_client(max_retries=0)`
  (Anthropic API under `anthropic`, Vertex Model Garden under `vertex`), Gemini ids use
  `provider.genai_client()`. It calls `provider.active_provider()` only to choose the server-tool
  variants (R6). Each client is built once per process (`functools.cache`, PERF-005); tests call
  `cache_clear()`.
- **Rationale**: One place for SDK-specific request shapes; call sites stay provider-free (AC 1,
  FR-014). Under `anthropic` only Claude ids are served (032), so family dispatch sends every call
  to the Anthropic API there; under `vertex` with the Gemini defaults nothing changes.
- **Alternatives**: dispatch on `active_provider()` (rejected in clarify Q1: a Claude id set for a
  role under `vertex` would crash in genai); a dispatch helper in `provider.py` (contract: 032 does
  not add dispatch there).

## R2. The text entry point (sc-252)

- **Decision**: `generate_text(prompt, role, *, max_tokens, policy, temperature=None,
  thinking=True) -> str`. The model is `provider.role_model(role)` (same value as the resolved
  `settings.wcl_*_model`, since `config.py` loads `.env` into the environment). The call runs inside
  `model_retry.generate_with_retry(..., policy)`; the caller keeps its own `asyncio` timeout.
  Policies (clarify Q3): suggestions and reports `RetryPolicy(attempts=1)`, titles their existing
  two-attempt `_POLICY`.
- **Gemini request**: `client.aio.models.generate_content(model, contents=prompt,
  config=GenerateContentConfig(max_output_tokens, temperature, thinking_config=ThinkingConfig(
  thinking_budget=0) if not thinking))`: byte-for-byte today's settings per call site (reports
  had no temperature/thinking config; titles 0.2 + budget 0; suggestions budget 0). Reports move
  from the blocking client in a thread to the async client (sc-252 AC 3).
- **Claude request**: `messages.create(model, max_tokens, messages=[user prompt])`; never
  `temperature` (400 on current models; from API version 2026-10-21 on every model). Thinking off
  (clarify Q2): Haiku ids get `thinking={"type": "disabled"}` (accepted at Haiku 5.5's default
  effort); other Claude ids get no `thinking` and `output_config={"effort": "low"}` (Opus 5.5 and
  Sonnet 5.5 reject `disabled`). The text is the concatenation of the `text` blocks. A `refusal`
  stop reason raises (fails closed at every call site).
- **Alternatives**: a model-id parameter instead of a role (AC 1 names a role); keeping
  `asyncio.to_thread` for reports (AC 3 says no thread when the async client suffices).

## R3. Structured output (sc-253 AC 3)

- **Decision**: `generate_json(model, prompt, schema, *, policy, temperature) -> str` returns the
  raw JSON text. Gemini: today's `response_mime_type="application/json"` + `response_schema=schema`
  + `temperature`. Claude: `output_config={"format": {"type": "json_schema", "schema":
  anthropic.transform_schema(schema)}}`, `max_tokens=16000` (the skill's non-streaming default),
  model-default thinking. `llm.generate_structured` keeps validation (`schema.model_validate_json`),
  the one retry on a misfit and `GuideModelError` unchanged.
- **Rationale**: `output_config.format` is the current structured-output API (forced
  `tool_choice` is a 400 on Opus/Sonnet 5.5). `transform_schema` is the SDK's own Pydantic →
  supported-JSON-schema conversion (adds `additionalProperties: false`, drops unsupported keywords).
  Our own validation keeps one rule for both providers.
- **Alternatives**: `messages.parse(output_format=schema)` (raises its own validation error, so the
  retry rule would split per provider); streaming with a larger cap (YAGNI: guide drafts fit well
  inside 16k; a truncated reply fails validation and gets the one retry).

## R4. Grounded research on Claude (sc-253 AC 4)

- **Decision**: `generate_grounded(model, prompt, *, fetch_domains, policy) -> Grounded(text,
  sources, search_errors)`. Under the Anthropic API: tools
  `{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}` and, when
  `fetch_domains` is non-empty, `{"type": "web_fetch_20260209", "name": "web_fetch",
  "max_uses": 5, "allowed_domains": [...]}`. `pause_turn` is resumed by re-sending
  `[user, assistant(content)]` at most 3 times; blocks from all responses are collected.
  Sources: every `web_search_result` (`title`, `url`) in `web_search_tool_result` blocks and each
  `web_fetch_result` (`url`, document `title`), in order of appearance, de-duplicated by URI (first
  wins), as `{title, uri}`.
  Error blocks (`web_search_tool_result_error`) are collected by `error_code`.
- **Rationale**: Dynamic-filtering variants are the skill's choice for Sonnet/Opus 5.5 (and Haiku
  5.5, "Claude 4.6 and later"); `max_uses` caps per-use billing; the doc says server-tool errors
  come back as 200 + error blocks, and a paused turn must be re-sent unchanged.
- **Failure rules**: (a) 400 `invalid_request_error` saying web search/fetch "is not enabled"
  → `ServerToolDisabled` with the fix ("an admin can enable it at
  https://platform.claude.com/settings/capabilities"), surfaced by `llm.py` as `GuideModelError`
  (run held). (b) Clarify Q4: at least one search error and zero search results →
  `llm.py` raises `GuideModelError("web search failed: <codes>")`. (c) Empty text →
  `GuideModelError` as today.
- **Alternatives**: sources from citations only (AC 4 says "from the results"); unbounded searches
  (cost).

## R5. Fetch rules are never bypassed (sc-253 AC 4, clarify Q5)

- **Decision**: `llm.generate_grounded(model, prompt, *, fetch_domains)` replaces the always-True
  `url_context` flag; `research.collect_evidence_basic` passes `fetch_domains=fetchable_domains()`
  (official domains always, guide sites only with `WCL_GUIDE_RESEARCH_FETCH_ENABLED`). Gemini turns
  URL context on iff the list is non-empty (always today, so unchanged) and stays prompt-restricted
  as today; Claude's web fetch is restricted server-side by `allowed_domains`.
- **Rationale**: one argument carries both "may fetch" and "where"; Claude gets a stricter
  guarantee than today. Two test fakes that declare `*, url_context` change their signature only.
- **Alternatives**: keep `url_context` and add `fetch_domains` (redundant flag); lazy import of
  `research` from `llm` (rejected in clarify Q5).

## R6. Claude on Vertex (family dispatch side effect)

- **Decision**: under `vertex`, a Claude guide model gets the basic `web_search_20250305` and no
  web fetch (not offered on Vertex); README says URL context is unavailable there.
- **Rationale**: the docs list only basic web search on Google-managed Vertex and no web fetch.

## R7. Tests without live calls (AC 6, SC-001)

- **Decision**: Claude paths run the real `AsyncAnthropic` client over an `httpx2.MockTransport`
  that returns scripted Messages API JSON (same technique as 032's `ScriptedApi`), so request
  bodies are asserted as sent and result blocks are parsed by the SDK. Gemini paths use object
  fakes for `client.aio.models.generate_content` (as the existing tests do). Existing tests that
  patched `suggestions._client`, `_SUGGEST_MODEL`, `vertex.genai_client` or `rs._generate` move to
  the `generation` seam with the same assertions. The sprint e2e file parametrises
  `vertex`/`anthropic` over the agent (032's scripted transport), suggestions, titles, reports and
  the guide steps, and holds the grep check.

## R8. Rejected for scope

- Server-side refusal `fallbacks` (skill default for Sonnet/Opus 5.5): the agent owns refusal
  handling (032); these calls fail closed. Backlog candidate if live checks show refusals.
- Chat web search on Claude (D3).
