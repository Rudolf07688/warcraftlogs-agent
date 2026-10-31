# Contract: the provider layer (`wcl_agent/llm/provider.py`)

Status: planned (032 `/speckit-plan`, 2026-10-31). Owner: 032 until it merges; later changes go
through the scrum master. Items marked **[uncertain]** may still change during 032's
implementation; 035 is told if they do.

## Rule

`wcl_agent/llm/provider.py` is the only module that reads `WCL_LLM_PROVIDER` and
`ANTHROPIC_API_KEY` and the only one that constructs model clients. Call sites ask it for a
client or a role's model. They never compare the provider name themselves. The guard test
(`backend/tests/test_vertex.py`) fails if `genai.Client(`, `Anthropic(`, `AsyncAnthropic(`,
`AnthropicVertex(` or `AsyncAnthropicVertex(` appears in `wcl_agent/` or `backend/app/` outside
this module.

## Types

```python
Provider = Literal["vertex", "anthropic"]

class ModelRole(StrEnum):
    CHAT = "chat"                  # WCL_DEFAULT_MODEL
    REPORT = "report"              # WCL_REPORT_MODEL
    GUIDE = "guide"                # WCL_GUIDE_MODEL         (guide author)
    GUIDE_REVIEW = "guide_review"  # WCL_GUIDE_REVIEW_MODEL
    FAST = "fast"                  # WCL_SUGGEST_MODEL       (suggestions, titles)
    GREETING = "greeting"          # WCL_GREETING_MODEL

ROLE_ENV: dict[ModelRole, str]                         # the table above
ROLE_DEFAULTS: dict[Provider, dict[ModelRole, str]]

class LlmProviderNotConfigured(RuntimeError): ...     # key-free message
```

| Role | `vertex` default | `anthropic` default |
|---|---|---|
| CHAT | `gemini-3.6-flash` | `claude-sonnet-5-5` |
| REPORT | `gemini-3.6-flash` | `claude-sonnet-5-5` |
| GUIDE | `gemini-3.7-flash` | `claude-sonnet-5-5` |
| GUIDE_REVIEW | `gemini-3.1-pro-preview` | `claude-opus-5-5` |
| FAST | `gemini-3.6-flash` | `claude-haiku-5-5` |
| GREETING | `gemini-3.5-flash-lite` | `claude-haiku-5-5` |

## Functions

```python
def active_provider() -> Provider
    # Cached per process. Tests: active_provider.cache_clear().

def role_model(role: ModelRole, explicit: str | None = None) -> str
    # explicit (else os.environ[ROLE_ENV[role]]), if served by the active provider, in its
    # id form; else ROLE_DEFAULTS[active][role]. Warns once per role for an unservable value.
    # Backend code reads the resolved values from settings instead:
    #   settings.wcl_default_model / wcl_report_model / wcl_guide_model /
    #   wcl_guide_review_model / wcl_suggest_model / wcl_greeting_model

def serves(model_id: str) -> bool
    # anthropic: Claude ids only; vertex: every id.

def to_provider_id(model_id: str) -> str
    # The one id-form conversion: dated Claude ids name@YYYYMMDD <-> name-YYYYMMDD into the
    # active provider's form; every other id unchanged.

def served_ids(ids: Iterable[str]) -> list[str]
    # [to_provider_id(m) for m in ids if serves(m)], de-duplicated, order kept.

def default_candidates() -> list[str]
    # Model ids to probe when nothing is configured: [] under vertex (today), the distinct
    # Claude role defaults under anthropic.

def has_model_catalog() -> bool
    # True only under vertex (the Model Garden listing). 033 changes this when it adds the
    # Anthropic Models API listing.

def credentials_error() -> str | None
    # None when the active provider has what it needs to build its clients; else one
    # key-free sentence (anthropic without ANTHROPIC_API_KEY). Logged once at startup.

# --- clients (the only constructors) ---
def anthropic_client(**kwargs) -> Anthropic | AnthropicVertex
def async_anthropic_client(**kwargs) -> AsyncAnthropic | AsyncAnthropicVertex
    # anthropic: Anthropic(api_key=<SecretStr>.get_secret_value(), **kwargs)
    # vertex:    AnthropicVertex(project_id=project_id(), region=model_location(), **kwargs)
    #            (the async Vertex client adds ADK's tracking headers itself)
    # Raises LlmProviderNotConfigured when credentials_error() is not None.
    # Callers pass max_retries=0 when they own retries (generate_with_retry does).

def genai_client() -> genai.Client
    # The Gemini client (Vertex at the model location, or the AI Studio key setup), as today.
    # Not provider-gated: under anthropic nothing in the app should call it once 035 lands.

def adk_client_kwargs() -> dict[str, Any]
    # client_kwargs for an ADK Gemini, as today.
```

## How a non-agent call site (035) gets a model and a client

1. The model: `settings.wcl_suggest_model` (suggestions, titles), `settings.wcl_report_model`,
   `settings.wcl_guide_model`, `settings.wcl_guide_review_model`. All are already resolved for the
   active provider. `role_model(ModelRole.X)` is the same value for code that has no settings.
2. The client: `async_anthropic_client(max_retries=0)` (Claude) or `genai_client()` (Gemini).
   Retries go through `model_retry.generate_with_retry`.
3. Which of the two to call is the one provider decision a text-generation entry point makes.
   **Decided (scrum master, 2026-10-31):** 035 owns a new `wcl_agent/llm/generation.py`, counted
   as part of the provider layer. It is the only module besides `provider.py` that may call
   `active_provider()`; the sprint grep check exempts both. 032 neither creates it nor adds
   dispatch to `provider.py`.
4. Don't build the entry point in 032. Don't send `temperature`/`top_p`/`top_k` to current Claude
   models (`claude-api` skill: they accept only the defaults), and don't force `tool_choice`
   (`any`/`tool` is a 400 on Opus 5.5 and Sonnet 5.5; use `output_config.format` for structured
   output).

## Transitional forwarders (to delete)

`wcl_agent/llm/vertex.py` keeps `genai_client()` and `anthropic_client(**kwargs)` as one-line
forwarders to this module (no logic), for callers 032 doesn't own. **To delete:** 033 moves
`wcl_agent/llm/models.py` to `provider` and deletes the `anthropic_client` forwarder; 035 moves
`backend/app/suggestions.py`, `services/report_synthesis.py` and `services/guide_pipeline/llm.py`
to `provider` and deletes the `genai_client` forwarder (`models.py` also uses `genai_client`, so
the last of 033/035 to merge deletes it). The scrum master grants `vertex.py` for the deletions.
`vertex.py` keeps `uses_vertex`, `model_location`, `project_id` and the catalog listing.

## Agent side (032 internal, for reference)

- `agent._retrying_model` is unchanged in shape: Claude ids get `RetryingClaude`, Gemini ids
  `RetryingGemini`. The provider decides the client inside `RetryingClaude._anthropic_client`.
- `RetryingClaude` adds `thinking.block_binding.prefix_mismatch_behavior="drop_block"` and the
  `anthropic-beta: thinking-binding-controls-2026-08-01` header when thinking is adaptive.
- `model_retry.is_anthropic_model(id)` stays the Claude-vs-Gemini family check (not a provider
  check).
