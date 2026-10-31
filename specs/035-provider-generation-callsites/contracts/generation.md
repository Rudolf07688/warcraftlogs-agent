# Contract: the generation entry points (`wcl_agent/llm/generation.py`)

Owner: 035. Part of the provider layer with `provider.py` (032): the only two modules that may
call `active_provider()`. Call sites import these functions and `provider.ModelRole`; they never
import `google.genai` or `anthropic`, never build clients and never branch on the provider.

## Functions

```python
async def generate_text(
    prompt: str,
    role: ModelRole,
    *,
    max_tokens: int,
    policy: RetryPolicy,
    temperature: float | None = None,   # Gemini only; never sent to Claude
    thinking: bool = True,              # False: Gemini budget 0; Claude per R2
) -> str
    # Model: provider.role_model(role). One call under generate_with_retry(policy).
    # Returns the reply text ("" when the model returns none). Raises the SDK error,
    # ModelRateLimited, or ModelRefused. The caller owns its timeout.

async def generate_json(
    model: str,
    prompt: str,
    schema: type[BaseModel],
    *,
    policy: RetryPolicy,
    temperature: float | None = None,
) -> str
    # The raw JSON text, constrained to `schema` (Gemini response_schema; Claude
    # output_config.format json_schema from anthropic.transform_schema). Not validated here.

async def generate_grounded(
    model: str,
    prompt: str,
    *,
    fetch_domains: Sequence[str],       # empty: no URL context / web fetch
    policy: RetryPolicy,
) -> Grounded
    # Gemini: google_search (+ url_context when fetch_domains), sources from grounding metadata.
    # Claude (Anthropic API): web_search_20260209 max_uses 10 (+ web_fetch_20260209 max_uses 5,
    # allowed_domains=fetch_domains); Claude on Vertex: web_search_20250305, no fetch.
    # pause_turn resumed at most 3 times. Raises ServerToolDisabled on the "not enabled" 400.
```

## Types

```python
@dataclass(frozen=True)
class Grounded:
    text: str                         # stripped reply text
    sources: list[dict[str, str | None]]  # [{"title", "uri"}], de-duplicated by uri, in order
    search_errors: list[str]          # Claude web_search error codes; always [] on Gemini

class ModelRefused(RuntimeError): ...       # Claude stop_reason "refusal"
class ServerToolDisabled(RuntimeError): ... # web search/fetch not enabled; message names the fix
```

## Thinking-off on Claude (clarify Q2)

| Model id | Request |
|---|---|
| `claude-haiku-*` | `thinking={"type": "disabled"}` |
| any other Claude id | no `thinking`, `output_config={"effort": "low"}` |

## Call-site use

| Call site | Entry point | Role / model | Policy | Other |
|---|---|---|---|---|
| `suggestions.generate_followups` | `generate_text` | `ModelRole.FAST` | attempts 1 | `max_tokens=256`, `thinking=False`, 4 s `wait_for` |
| `conversation_titles.generate_title` | `generate_text` | `ModelRole.FAST` | existing `_POLICY` (2) | `max_tokens=32`, `temperature=0.2`, `thinking=False`; 15 s in `retitle_conversation` |
| `report_synthesis.synthesize_findings` | `generate_text` | `ModelRole.REPORT` | attempts 1 | `max_tokens=16_384`, 60 s `wait_for`, no thread |
| `guide_pipeline.llm.generate_structured` | `generate_json` | `settings.wcl_guide_model` / `wcl_guide_review_model` (callers) | `llm._policy()` | validation + one retry + `GuideModelError` stay in `llm.py` |
| `guide_pipeline.llm.generate_grounded` | `generate_grounded` | `settings.wcl_guide_model` | `llm._policy()` | `fetch_domains=research.fetchable_domains()`; `GuideModelError` on errors, empty text, or search errors with no results |
