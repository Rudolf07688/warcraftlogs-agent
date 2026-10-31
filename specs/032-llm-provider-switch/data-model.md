# Data model: LLM provider switch (032)

No database change and no migration. Everything below is process configuration and in-memory
values.

## Provider

`Provider = Literal["vertex", "anthropic"]`. One value per process, from `WCL_LLM_PROVIDER`
(trimmed, case-insensitive). Unset means `vertex`. Any other value means `vertex`, with one warning.
Cached for the process; tests clear the cache.

## ModelRole

`ModelRole` (a `StrEnum`), one fixed use of a model:

| Role | Value | Env variable | Read by |
|---|---|---|---|
| `CHAT` | `chat` | `WCL_DEFAULT_MODEL` | `Settings.wcl_default_model`, `agent.DEFAULT_MODEL` |
| `REPORT` | `report` | `WCL_REPORT_MODEL` | `Settings.wcl_report_model` |
| `GUIDE` | `guide` | `WCL_GUIDE_MODEL` | `Settings.wcl_guide_model` |
| `GUIDE_REVIEW` | `guide_review` | `WCL_GUIDE_REVIEW_MODEL` | `Settings.wcl_guide_review_model` |
| `FAST` | `fast` | `WCL_SUGGEST_MODEL` | `Settings.wcl_suggest_model` (new; 035 switches suggestions/titles to it) |
| `GREETING` | `greeting` | `WCL_GREETING_MODEL` (new) | `Settings.wcl_greeting_model` (new), `greeting.GREETING_MODEL` |

Defaults per provider (`ROLE_DEFAULTS`):

| Role | `vertex` | `anthropic` |
|---|---|---|
| chat | `gemini-3.6-flash` | `claude-sonnet-5-5` |
| report | `gemini-3.6-flash` | `claude-sonnet-5-5` |
| guide | `gemini-3.7-flash` | `claude-sonnet-5-5` |
| guide_review | `gemini-3.1-pro-preview` | `claude-opus-5-5` |
| fast | `gemini-3.6-flash` | `claude-haiku-5-5` |
| greeting | `gemini-3.5-flash-lite` | `claude-haiku-5-5` |

Resolution: an explicit value (stripped, non-empty), if the active provider serves it, in the
active id form. Otherwise the provider default. A non-empty unservable value logs one warning per
role per process.

## Model id forms

| Form | Example | Served by |
|---|---|---|
| Gemini | `gemini-3.6-flash` | `vertex` only |
| Claude, undated | `claude-sonnet-5-5` | both, same string |
| Claude, API dated | `claude-sonnet-4-20250514` | `anthropic`; under `vertex` read as `claude-sonnet-4@20250514` |
| Claude, Vertex dated | `claude-sonnet-4@20250514` | `vertex`; under `anthropic` read as `claude-sonnet-4-20250514` |

`serves(id)`: under `anthropic`, Claude ids only (`is_anthropic_model`); under `vertex`, every id.
`to_provider_id(id)` converts only the dated Claude forms; every other id passes through.

## Settings changes (`backend/app/config.py`)

- Role fields `wcl_default_model`, `wcl_report_model`, `wcl_guide_model`,
  `wcl_guide_review_model` default to `""`. New `wcl_suggest_model`, `wcl_greeting_model`
  (`""`). An after-validator resolves all six through `role_model`, so every reader sees a
  concrete id.
- `llm_provider` (property): `provider.active_provider()`.
- `gemini_models`, `anthropic_models`, `model_list`: through `provider.served_ids()`; under
  `anthropic`, an empty Claude list becomes `provider.default_candidates()`. Unchanged under
  `vertex`.
- `model_discovery_mode`: `static` when `provider.has_model_catalog()` is false.

## Errors

`LlmProviderNotConfigured(RuntimeError)`: raised by the Claude client builders when the active
provider lacks its credential (`anthropic` with no key). Its message is fixed text naming
`ANTHROPIC_API_KEY`; it never contains a key value.
