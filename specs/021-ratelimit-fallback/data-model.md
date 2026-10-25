# Data Model: Rate-Limit Fallback to the Sibling Model (021)

No database change. Everything here is in-process, per turn.

## TurnStats (dataclass, `wcl_agent/llm/model_retry.py`): new fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `fallback_model` | `str \| None` | `None` | The sibling this turn may switch to once. Set only by the chat socket (via `stream_response(fallback_model=...)`); `None` means "no fallback" (helpers, CLI, no sibling). |
| `switched_to` | `str \| None` | `None` | Set once, when the switch happens; after that every request of the turn for `model` is routed here. A second rate limit is never switched again. |
| `switch_index` | `int \| None` | `None` | `len(llm_request.contents)` at the switch: the end of the current-turn span whose Gemini thought signatures were produced by the original model (research R5). |

State transitions within one turn:

```text
no switch (switched_to=None) --ModelRateLimited on stats.model, fallback_model set--> switched (switched_to=fallback_model)
no switch --ModelRateLimited, fallback_model None--> turn fails: rate_limited
switched  --ModelRateLimited on the sibling--> turn fails: rate_limited
```

## Stream record (runner → socket): `model_fallback`

`{"type": "model_fallback", "from_model": str, "to_model": str}`, emitted once per turn
through `TurnStats.emit`, at the moment of the switch (before the sibling's first
attempt).

## ModelFallbackFrame (Pydantic, `backend/app/schemas.py`)

| Field | Type | Notes |
|---|---|---|
| `type` | `Literal["model_fallback"]` | |
| `from_model` | `str` | The rate-limited model (the player's choice). |
| `to_model` | `str` | The sibling that continues the turn. |

## Frontend `Message` (`frontend/src/types.ts`): new optional field

| Field | Type | Notes |
|---|---|---|
| `fallback` | `{ from: string; to: string } \| undefined` | Set on the agent message when its turn switched. Live session only (not loaded from the API). |

## Sibling resolution (functions, `wcl_agent/llm/models.py`)

- `model_class(model_id) -> tuple[str, str] | None`: `("google", "flash")`,
  `("anthropic", "sonnet")`, or `None` for an id outside the discovery naming. A
  `name@version` Claude id is classified by its name.
- `sibling_model(model, served) -> str | None`: peers = served ids with the same
  `model_class`, in served order; first peer → second peer (or `None`), other peer →
  first peer; `None` if `model` is unknown or not served.
