# Contract: Configuration

## New settings

| Variable | Default | Values / format | Effect |
|---|---|---|---|
| `WCL_MODEL_DISCOVERY` | `catalog` | `catalog` \| `static` | `static` = today's probing of the `.env` lists only |
| `WCL_GEMINI_CLASSES` | `pro:2,flash:2,flash-lite:2` | `class:count,…`; classes `pro`, `flash`, `flash-lite` | Classes to offer, in serving order, and how many of each to keep |
| `WCL_ANTHROPIC_CLASSES` | `haiku:1,sonnet:1,opus:1` | classes `haiku`, `sonnet`, `opus` | As above for Claude. Empty = no Claude. |
| `WCL_MODEL_LOCATION` | `global` | a Vertex location | Where every model call runs: chat, web search, guides, reports, greeting, suggestions, probes |
| `WCL_CACHE_TTL_MODEL_CATALOG` | `21600` | seconds; `0` = don't store | Lifetime of the shared discovery result (existing per-family TTL mechanism) |

## Changed

| Variable | Before | After |
|---|---|---|
| `GOOGLE_CLOUD_LOCATION` (`.env.example`) | `global` | `europe-west1`. No longer used for model calls. |
| `WCL_ANTHROPIC_REGION` | Claude region override; the code fell back to `us-east5` | **Removed**. Claude uses `WCL_MODEL_LOCATION`. |

## Unchanged, with a new role

| Variable | Role after this feature |
|---|---|
| `WCL_GEMINI_MODELS`, `WCL_ANTHROPIC_MODELS` | Static-mode candidates, and the fallback when the catalog can't be listed |
| `WCL_MODELS` | Degraded list (nothing passed) |
| `WCL_DEFAULT_MODEL` | Preferred default. If it isn't served, the newest flash model is the default. |
| `WCL_GUIDE_MODEL`, `WCL_GUIDE_REVIEW_MODEL`, `WCL_REPORT_MODEL` | Fixed, never taken from the dropdown. A startup warning is logged if one is absent from the catalog. |

## Invalid input

- An unknown class name, or a count that isn't a positive integer: that entry is ignored
  and one WARNING is logged at startup.
- `WCL_MODEL_DISCOVERY` with any other value: treated as `catalog`, with a WARNING.
