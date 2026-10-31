# Contract: configuration (env variables)

| Variable | Values / default | Notes |
|---|---|---|
| `WCL_LLM_PROVIDER` | `vertex` (default) or `anthropic` | Trimmed, case-insensitive. Anything else: one warning, `vertex`. Restart to switch. |
| `ANTHROPIC_API_KEY` | empty | Secret. Needed under `anthropic`. Missing: one startup error, degraded model list, app stays up. Never logged or returned. |
| `WCL_DEFAULT_MODEL` | role default | Chat default. Explicit value wins only if the active provider serves it. |
| `WCL_REPORT_MODEL` | role default | Findings-report synthesis. |
| `WCL_GUIDE_MODEL` | role default | Guide author. |
| `WCL_GUIDE_REVIEW_MODEL` | role default | Guide reviewer; must differ from the author (startup warning as today). |
| `WCL_SUGGEST_MODEL` | role default | Suggestions and titles (035 moves those call sites onto the role). |
| `WCL_GREETING_MODEL` | role default | New. The greeting model (was a fixed constant). |
| `WCL_ANTHROPIC_MODELS` | empty | Static candidates. Under `anthropic`, read in API form; empty means the Claude role defaults. |
| `WCL_GEMINI_MODELS`, `WCL_MODELS` | as today | Under `anthropic`, Gemini ids are ignored. |
| `WCL_MODEL_DISCOVERY` | `catalog` | Under `anthropic` until 033, discovery runs `static` (the catalog is Vertex's). |
| `GCP_ADC_FILE` | gcloud default path | Without ADC under `anthropic`, set to `/dev/null` so compose mounts an empty file. |

Role defaults per provider: see `provider-layer.md`.

Startup log lines (backend):

- `INFO LLM provider: anthropic` (or `vertex`), once.
- `WARNING WCL_LLM_PROVIDER='openai' is not vertex or anthropic; using vertex`, once, for an invalid value.
- `WARNING WCL_DEFAULT_MODEL=gemini-3.6-flash is not served by the anthropic provider; using claude-sonnet-5-5`, once per role.
- `ERROR WCL_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set; Claude calls fail until it is set in .env and the backend restarts`, once, when the key is missing.

WebSocket: a chat turn naming an unserved model no longer gets `invalid_model`; it runs on the
default (one `INFO` line). REST endpoints keep their 400.
