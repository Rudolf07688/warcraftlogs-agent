# Research: Rate-Limit Fallback to the Sibling Model (021)

All findings were read from the installed packages in the worktree venv
(`google-adk 2.10.0`, `google-genai`, `anthropic`) and from the code at base `cc3c783`.
Paths below are relative to `.venv/lib/python3.14/site-packages/google/adk/`.

## R1. Fallback level: per request, not a turn re-run

- **Decision**: Fall back per model request, inside the ADK model wrappers
  (`RetryingGemini` / `RetryingClaude` in `wcl_agent/llm/model_retry.py`). When a request
  raises `ModelRateLimited` (the feature 011 retries are spent and nothing of that
  request's response was yielded), the wrapper switches the request's model to the
  sibling and runs the same request again on it. The turn then carries on.
- **Rationale**:
  - The ADK session already holds the turn's user message, its tool calls and results,
    and any text streamed by earlier requests of the turn. Re-running the whole turn
    would append the user message again and repeat every lookup, and the WebSocket
    layer would have to discard tokens already shown. A per-request switch re-runs
    nothing: the session gets each event exactly once (AC 4, FR-006).
  - `ModelRateLimited` is raised by `generate_with_retry` only on the `not yielded`
    branch, so the switch can never duplicate streamed text. A rate limit that arrives
    mid-stream re-raises the raw error as today (Q5 = A).
  - It reuses the existing retry loop and its `model_retry` status records on the
    sibling as well, with no second waiting mechanism.
- **Alternatives considered**: a turn-level re-run in `stream_response` (AC 4 allows it).
  Rejected: it duplicates the user message in the ADK history, needs session surgery to
  drop the failed attempt's events, and repeats tool calls (cost and WCL quota).

## R2. Does mutating `llm_request.model` reach the client call? (scrum master condition)

Yes, on both paths. Each step builds a fresh request, and the model id is read from the
request, not from the model object, at call time.

- **Fresh request per step**: `flows/llm_flows/base_llm_flow.py:394`,
  `llm_request = LlmRequest()` in `_run_one_step_async` ("One step means one LLM call").
- **Model id set from the agent each step**: `flows/llm_flows/basic.py:106-107`,
  `model = agent.canonical_model` then `llm_request.model = model.model`. So every new
  request of the turn starts on the agent's model (the player's choice), and the wrapper
  must route later requests itself after a switch (R4).
- **Gemini** (`models/google_llm.py`):
  - `:241`, `model = llm_request.model` inside `Gemini.generate_content_async` (after
    `_preprocess_request`, `:239`).
  - `:297-298`, streaming: `self.api_client.aio.models.generate_content_stream(model=model, ...)`.
  - `:354-355`, non-streaming: `self.api_client.aio.models.generate_content(model=model, ...)`.
  - `:425-457`, `api_client` is built without any model id (a per-event-loop
    `genai.Client`), so one client serves both siblings.
- **Claude** (`models/anthropic_llm.py`):
  - `:1022`, `model_to_use = self._resolve_model_name(llm_request.model)` inside
    `_build_anthropic_kwargs` (`:993`); `:981-991`, `_resolve_model_name` returns the
    request's id (only a `projects/...` path is shortened; an empty id falls back to
    `self.model`).
  - `:1119-1122`, non-streaming: `kwargs = self._build_anthropic_kwargs(llm_request, ...)`
    then `client.messages.create(**kwargs)`.
  - `:1158-1164`, streaming: the same kwargs into `client.messages.create(stream=True, **kwargs)`.
  - The client (`RetryingClaude._anthropic_client`, our override) is model-agnostic.
- **Consequence**: the wrapper's retry lambda,
  `lambda: super(...).generate_content_async(llm_request, stream)`, reads
  `llm_request.model` lazily on every attempt. Setting it to the sibling before the next
  call is enough; no second model object or client is needed. A test drives each path
  with a fake client that records the `model` argument it receives (plan T-tests).

## R3. Sibling resolution

- **Decision**: A pure function in `wcl_agent/llm/models.py`:
  `model_class(model_id) -> (publisher, class) | None`, using the existing `_GEMINI_RE` /
  `_CLAUDE_RE` (the same naming rules discovery uses), and
  `sibling_model(model, served) -> str | None`. Peers are the served models of the same
  publisher and class, in served order. For the first peer the sibling is the second
  (if any); for any other peer it is the first. `backend/app/model_state.py` gets
  `fallback_model_for(app, model)`, which applies it to the served set from `app.state`.
- **Rationale**: Discovery already serves each class newest first (feature 016,
  `pick_per_class`), and `app.state.models` is the single source of truth for what is
  selectable (`model_state.get_model_state`). Classifying by id needs no new state and no
  change to `main.py` or the cached `ModelCatalog`. It works in static mode too, where
  configured ids follow the same naming. Unknown ids (no regex match) get no sibling.
- **Alternatives considered**: storing `catalog.classes` on `app.state` (needs `main.py`
  and is empty in static mode); a configured sibling map (a new setting with no present
  need).
- **Claude** (Q3 = A): one rule for both publishers. Today's Claude classes serve one
  model each, so `sibling_model` returns `None` and the turn ends with the feature 011
  message (decision 7).

## R4. One switch per turn, and routing later requests

- **Decision**: `TurnStats` gains `fallback_model: str | None` (set by the chat socket
  only) and `switched_to: str | None`. The wrapper acts only on requests for the turn's
  own model (`llm_request.model == stats.model`), so the `web_search` sub-agent (a plain
  `Gemini`, not a retrying wrapper, `wcl_agent/agent.py:466`) and helper calls are never
  touched. On the first `ModelRateLimited` with `fallback_model` set and
  `switched_to is None`, it sets `switched_to`, emits one `model_fallback` record, and
  re-runs the request on the sibling. Every later request of the turn that arrives with
  `stats.model` is routed to `switched_to` before its first attempt. A `ModelRateLimited`
  on the sibling propagates unchanged, so the socket sends the feature 011 message
  (FR-003, FR-004, AC 3).
- **Rationale**: `TurnStats` is already the per-turn state installed in `current_turn`
  and inherited by the ADK tasks; one more field keeps the switch per turn without new
  plumbing. Helper paths (greeting, guild summary, guide pipeline, titles) never set
  `fallback_model`, so they behave exactly as before (FR-009).

## R5. Gemini thought signatures after a mid-turn switch

- **Finding**: Gemini 3 models attach a `thought_signature` to function-call parts and
  validate the signatures of the *current* turn's function calls on the next request.
  Google's guidance for traces that come from another model is to send the documented
  bypass value `skip_thought_signature_validator` in place of the signature. Earlier
  turns are not validated, which is why switching models in the selector between turns
  already works today.
- **Decision**: When a Gemini request is routed to the sibling, parts of the current turn
  that the original model produced before the switch (contents from the turn's user
  message up to the switch point) have their `thought_signature` replaced by the bypass
  value. This is done on new `Content`/`Part` copies in that request only. The stored
  session events are never mutated, the same rule `inject_preamble` follows. Parts the
  sibling produces after the switch keep their own valid signatures. Claude has no
  sibling today, so the Anthropic path needs nothing.
- **Rationale**: Without it, the sibling may reject the switched request with a 400
  exactly when the fallback is needed. It cannot be confirmed without a live Vertex call
  (no credentials in the sprint worktree), so the guard is cheap insurance, covered by a
  unit test and listed for the owner's live check in quickstart.md.
- **Alternatives considered**: no sanitising (risk above); dropping the parts (would
  lose the turn's evidence).

## R6. The notice (Q1 = A, Q2 = A, provisional)

- **Decision**: A new typed frame `model_fallback {from_model, to_model}`
  (`ModelFallbackFrame`, appended to `backend/app/schemas.py`), forwarded by `ws.py`
  right when the switch happens. The frontend shows it in the live status line while
  streaming, and on `done` attaches it to the agent message, rendered as a small note
  under the reply. It uses the same pattern as the existing "Used web search" note.
  Not stored, so a reload does not show it. The model selector is unchanged, and the
  next turn starts on the chosen model.
- **Rationale**: Reusing `model_retry` for the notice would overload its meaning
  (attempt counters) and its existing label. `grounding` is forwarded untyped today, but
  constitution IV asks for a typed frame. No database change (Q1 = A).

## R7. Impact (GitNexus, worktree re-indexed at cc3c783)

| Symbol | Risk | Direct callers | Our change |
|---|---|---|---|
| `stream_response` | CRITICAL | `ws._handle_turn`, `greeting._generate_greeting`, `services/guide._stream_text`, `evals/guides/coaching.run_case` | Adds one keyword-only `fallback_model=None`; default keeps today's behaviour. |
| `generate_with_retry` | CRITICAL | `conversation_titles.generate_title`, `guide_pipeline/llm._generate`, both wrappers | **Unchanged.** |
| `make_before_model_callback` | HIGH | `agent.build_agent` | **Unchanged.** The callback fires once per request before the wrapper, so a switched request is counted once and keeps its injected preamble. |
| `RetryingGemini` / `RetryingClaude` / `TurnStats` | MEDIUM | file imports (agent, runner, ws, titles) | Wrapper bodies call the new `generate_with_fallback`; `TurnStats` gains defaulted fields only. |
| `_handle_turn` | LOW | `_start_turn` then `chat` | Gains keyword `fallback_model=None`, and forwards one more record type. |
