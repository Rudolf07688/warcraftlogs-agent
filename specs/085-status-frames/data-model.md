# Data model: 085

No schema change, no migration.

## Partial agent message (existing `messages` row, status `partial`)
- Text = the answer tokens after the turn's last `interim`.
- New case: a turn ended by a socket drop after a retraction with no tokens kept stores text "(no response)".
- Never contains text that preceded an `interim` (any end: cancel, drop, error).

## Live turn status (browser only, `frontend/src/lib/statusStore.ts`)
| field | type | set by | cleared by |
|---|---|---|---|
| status | string | tool_start (tool label), grounding, model_retry/model_fallback (label) | turn end → "Thinking" |
| thought | string \| null | thinking, interim | tool_end, model_retry/fallback, turn end |
| notice | string \| null | model_retry, model_fallback | tool_start, tool_end, thinking, interim, grounding, turn end |
| quietSince | ms epoch | every non-token frame, turn start | — |

All text fields: controls stripped, ≤ 120 code points.
