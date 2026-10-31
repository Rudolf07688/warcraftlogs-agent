# Research: LLM provider switch (032)

All findings are from the installed packages (`anthropic` 1.11.0, `google-adk` 2.10.0) and fake
clients. No live LLM call was made.

## R1. Can `RetryingClaude` run on a plain `AsyncAnthropic`?

- **Decision**: Yes, with a client swap only. `RetryingClaude._anthropic_client` returns the
  provider layer's async Claude client (`AsyncAnthropic` under `anthropic`, `AsyncAnthropicVertex`
  under `vertex`). The class keeps its ADK base (`Claude`).
- **Rationale**: ADK's `AnthropicLlm` (the base of `Claude`) types `client` as
  `AsyncAnthropic | AsyncAnthropicVertex` and sends every request through
  `client.messages.create(**kwargs)`. `Claude` only adds a Vertex-only `_anthropic_client`, which
  `RetryingClaude` already overrides in full, so the `isinstance(AsyncAnthropicVertex)` check never
  runs. A full ADK turn (`InMemoryRunner`) with a fake `AsyncAnthropic` reached the client with all
  21 tool declarations and the model id unchanged.
- **Alternatives**: Rebase `RetryingClaude` on `AnthropicLlm`. It works too, but it changes the
  class hierarchy for no behavioural gain (constitution III).

## R2. Claude agent turns fail before any request (pre-existing)

- **Finding**: `build_agent` gives every model a `BuiltInPlanner` with
  `ThinkingConfig(include_thoughts=True)` and no `thinking_budget`. ADK 2.10's Anthropic adapter
  (`_build_anthropic_thinking_param`) raises `ValueError("thinking_budget must be set explicitly…")`
  for that config, so every Claude turn fails on both providers today (reproduced with a fake
  client).
- **Decision**: For Claude ids, the planner gets `ThinkingConfig(include_thoughts=True,
  thinking_budget=-1)`. ADK maps a negative budget to `{"type": "adaptive", "display":
  "summarized"}`, which the current Claude models require. Gemini's config is unchanged. Thought
  parts are already filtered out of the streamed answer by the runner.
- **Effect**: Claude on Vertex works again (the hand-off says so; the owner checks it live).

## R3. Thinking blocks and the app's history edits

- **Finding** (`claude-api` skill, model-migration "preserved thinking"): on Claude Fable 5.1 and
  the 5.5 models, a replayed thinking block is valid only while everything before it (system,
  tools, earlier messages) is unchanged. For accounts created on or after 2026-08-31 (every
  platform), a request that replays an invalidated block gets a 400. ADK replays thinking blocks
  with their signatures. The app edits history on every request: `context_trim` stubs old tool
  results, the per-turn preamble is injected and later dropped, and `build_instruction` stamps the
  time to the minute.
- **Decision**: `RetryingClaude` adds `thinking.block_binding.prefix_mismatch_behavior =
  "drop_block"` and the `anthropic-beta: thinking-binding-controls-2026-08-01` header to every
  request whose thinking is adaptive (an override of ADK's `_build_anthropic_kwargs`, which both
  the streaming and the non-streaming path call). The API then drops the invalidated blocks and
  proceeds. The beta is documented for the Claude API and Vertex (HTTP header), and
  `block_binding` works with adaptive thinking on Opus 5.5, Sonnet 5.5 and Haiku 5.5.
- **Alternatives**: Strip thinking blocks client-side (the skill says don't: it can cause
  ordering/signature 400s and loses reasoning). Make history append-only (a redesign of
  `context_trim` and the preamble, out of scope). Do nothing (multi-request turns fail on new
  accounts).
- **Uncertainty**: verified against the skill's documentation and request shape only; the owner's
  live check confirms it.

## R4. Where the provider layer lives, and the forwarders

- **Decision**: New module `wcl_agent/llm/provider.py`. It is the only code that reads
  `WCL_LLM_PROVIDER` and the key, the only code that constructs model clients (`genai.Client`,
  `Anthropic`, `AsyncAnthropic`, `AnthropicVertex`, `AsyncAnthropicVertex`), and it owns the model
  roles and id forms. `vertex.py` keeps what is Vertex-only (model location, project, the Model
  Garden catalog listing).
- **Forwarders**: `vertex.genai_client()` and `vertex.anthropic_client()` stay as two-line
  forwarders to the provider layer, because their callers belong to 033 (`models.py`, the
  discovery probes) and 035 (suggestions, report synthesis, guide LLM). Through the forwarder, the
  unchanged discovery probe reaches the Anthropic API under `anthropic`. 033 and 035 move those
  callers to `provider` and delete the forwarders.
- **Guard test**: `test_vertex.py::test_no_model_client_is_built_outside_vertex` becomes
  "outside provider.py" and also matches `Anthropic(` / `AsyncAnthropic(`.
- **Alternatives**: Keep all builders in `vertex.py` and make it provider-aware (a module named
  "vertex" building Anthropic API clients misleads). Edit `models.py` (033 owns it).

## R5. The key as a secret

- **Decision**: The provider layer reads `ANTHROPIC_API_KEY` from the environment into a pydantic
  `SecretStr` and passes `api_key=…get_secret_value()` straight into the client constructor. No
  other code holds the value; `Settings` doesn't get a field for it (a second reader would be dead
  code).
- **Checked**: `AsyncAnthropic()` with no key constructs without error (fails only at request time),
  so the provider checks for the key itself and raises `LlmProviderNotConfigured` with a fixed,
  key-free message. With a sentinel key and a mock transport answering 401, the SDK's
  `AuthenticationError` (`str`, `repr`, formatted traceback) and the client's `repr` don't contain
  the key.
- **Leak surface**: the WebSocket `agent_error` frame sends `str(exc)` (existing behaviour); both
  exception types above are key-free. The leak test asserts the sentinel is absent from captured
  logs, frames, `/api/*` bodies and exception text.

## R6. Interim discovery under `anthropic` (until 033)

- **Decision**: Settings properties, not `_load_models`, make discovery provider-aware.
  - `model_discovery_mode` returns `static` whenever the active provider has no catalog (the
    Model Garden listing is Vertex-only), with one info log line.
  - `gemini_models`, `anthropic_models` and `model_list` pass through `provider.served_ids()`
    (unservable ids dropped, the rest converted to the active form). Under `anthropic`, an empty
    Claude list becomes `provider.default_candidates()` (the distinct Claude role defaults).
  - Under `vertex` each property returns exactly what it returns today.
- **Result**: `_load_models` probes the Claude ids through the Anthropic API (via the forwarder in
  R4) and never touches the Vertex catalog or `project_id()`. With no key the client build fails,
  the probe step doesn't run, and the degraded Claude list is served.

## R7. Role resolution

- **Decision**: `provider.role_model(role, explicit=None)` resolves one role: an explicit value
  (argument, else the role's env variable), if servable, in the active form; else the provider
  default. An unservable explicit value is warned once per role per process. `Settings` keeps
  its role fields (tests monkeypatch them) with empty defaults, and a `model_validator(mode="after")`
  fills each one through `role_model`. New fields: `wcl_suggest_model`, `wcl_greeting_model`.
  `agent.DEFAULT_MODEL` and `greeting.GREETING_MODEL` read the resolved role.
- **Rationale**: one resolution function, call sites unchanged (they keep reading
  `settings.wcl_report_model` etc.), and the switch needs one `.env` line.

## R8. Stale model ids

- **Backend (WS only)**: new `model_state.resolve_chat_model(app, model)` returns the id in the
  active form if it is served, else the default (one info log). `ws.chat` replaces the
  `invalid_model` branch with it. REST callers keep `is_valid_model` and their 400.
- **Frontend (PO condition, D9)**: `App.tsx` already resets an unserved selection to the served
  default (line 317, after `/api/models`) and continues a reopened chat on the default
  (line 342). A new test file renders `App` with mocked `restClient`, `wsClient` and `useAuth`
  and asserts the socket payload's `model` in both cases. `App.tsx` is not edited.

## R9. Compose without an ADC file

- **Finding**: the backend's ADC mount uses the short bind syntax; Docker creates the missing host
  path as an empty directory, so compose still starts. Under `anthropic` no LLM path calls
  `google.auth` (static discovery, the API client). Until 035, suggestions, titles and reports
  still use Gemini and fail closed without ADC (their existing behaviour).
- **Decision**: no compose change. README tells owners without ADC to set `GCP_ADC_FILE=/dev/null`,
  so Docker doesn't create a directory at the gcloud default path.

## R10. Other API facts that matter later (for 033/035, not built here)

- Current ids: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`; undated ids are the same
  on the API and Vertex, and dated ones differ (`name-YYYYMMDD` vs `name@YYYYMMDD`).
- The current models accept only default sampling: don't send `temperature`/`top_p`/`top_k`
  (ADK already omits them when thinking is adaptive). Relevant to 035's `temperature=0.0` calls.
- Forced `tool_choice` (`any`/`tool`) returns a 400 on Opus 5.5 and Sonnet 5.5 (035, structured
  output: use `output_config.format` instead).
