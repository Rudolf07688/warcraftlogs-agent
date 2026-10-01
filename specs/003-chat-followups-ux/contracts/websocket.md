# WebSocket Contract Additions — 003-chat-followups-ux

Extends the existing `/ws/chat` contract (feature 001/002). **All additions are backward
compatible**: a new server→client frame type only; clients that don't recognize it ignore
it. Existing frames (`meta`, `token`, `tool_start`, `tool_end`, `grounding`,
`raid_tracked`, `done`, `error`) and the client→server `ChatTurn` are unchanged.

## New server → client frame: `suggestions`

Emitted **once per turn**, **after** all `token` frames and **immediately before**
`done`, only when the agent produced at least one follow-up. Omitted when there are none.

```jsonc
{
  "type": "suggestions",
  "suggestions": ["What are the parse scores for everyone?",
                  "Who took the most avoidable damage?",
                  "How do I improve my rotation?"]
}
```

Rules:
- `suggestions` is an array of **0–3** strings; the server MUST NOT emit more than 3.
- If the list would be empty, the server MUST NOT send the frame at all.
- Each string is the full prompt text submitted verbatim when its button is clicked.

Pydantic (backend `schemas.py`):

```python
class SuggestionsFrame(BaseModel):
    type: Literal["suggestions"] = "suggestions"
    suggestions: list[str] = Field(default_factory=list, max_length=3)
```

Frontend `Frame` union (`wsClient.ts`) gains:

```ts
| { type: "suggestions"; suggestions: string[] }
```

## Turn frame ordering (updated)

```
meta → (tool_start | tool_end | grounding | token | raid_tracked)* → [suggestions] → done
                                                                      └ optional
```

On `error`, no `suggestions` frame is sent for that turn.

## Parallel tool execution behavior (confirmation, not wire change)

No frame changes. The server MUST:
- Execute independent tool calls from a single model turn **concurrently** (verified by
  test, not assumed).
- Preserve each tool's **complete** result (including multi-MB payloads) via the per-turn
  shared scratch store and make it available to the agent before composing the answer.
- On a **single** tool failure, continue using the other tools' results and surface the
  failure in the answer rather than aborting the turn (no extra error frame required for a
  partial tool failure; a turn-fatal failure still uses the existing `error` frame).

## Click-to-prompt flow

A clicked suggestion is sent as an ordinary `ChatTurn` (same `conversation_id`, current
`model`, `content` = suggestion text). No new client→server message type. Suggestion
buttons MUST be disabled/queued while a turn is streaming (no interleaved turns).
