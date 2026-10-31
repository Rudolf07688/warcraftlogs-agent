# Data model: 035

No database or API schema changes. In-process value objects only (constitution IV).

| Type | Kind | Fields | Where |
|---|---|---|---|
| `Grounded` | frozen dataclass | `text: str`, `sources: list[{title, uri}]`, `search_errors: list[str]` | `wcl_agent/llm/generation.py` |
| `GroundedText` | frozen dataclass (unchanged) | `text`, `sources` | `guide_pipeline/llm.py`; built from `Grounded` |
| `ModelRole` | StrEnum (032) | `FAST`, `REPORT`, `GUIDE`, `GUIDE_REVIEW`, ... | `wcl_agent/llm/provider.py` (read only) |
| `RetryPolicy` | dataclass (011) | attempts, delays, budget | `wcl_agent/llm/model_retry.py` (read only) |

Rules:

- `sources` is de-duplicated by `uri`, order of first appearance; `title` may be `None`.
- `search_errors` holds Claude `web_search_tool_result_error.error_code` values; Gemini always `[]`.
- The guide step schemas (`_AuthorDraft`, `_ReviewDraft`, `_Extraction`) are unchanged and are
  the single validation contract on both providers.
