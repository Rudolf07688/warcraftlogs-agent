# Contract: WebSocket Chat Stream

**Endpoint**: `GET /ws/chat` (WebSocket upgrade)

Carries one user turn at a time and streams the agent's response back incrementally.
All frames are JSON text messages. Pydantic models validate both directions.

## Client → Server (one per user turn)

```jsonc
{
  "conversation_id": "uuid-or-null",   // null => create a new conversation
  "model": "gemini-3.6-flash",          // selected model id (must be in allow-list)
  "content": "How are hunters performing on Heroic Ula'tek?"
}
```

Rules:
- `content` MUST be non-empty (empty → `error` frame, no persistence).
- If `conversation_id` is null, the server creates a conversation (using `model`)
  and returns its id in the first `meta` frame.
- Sending a new turn while one is still streaming on the same socket is rejected
  with an `error` frame (`code: "busy"`).

## Server → Client (stream of frames)

Frames share a `type` discriminator:

```jsonc
{ "type": "meta",       "conversation_id": "uuid", "seq": 2 }         // first frame of a turn
{ "type": "tool_start", "name": "get_rankings_distribution" }         // agent called a tool
{ "type": "tool_end",   "name": "get_rankings_distribution", "ok": true }
{ "type": "token",      "text": "On Heroic Ula'tek" }                 // append to current agent message
{ "type": "done",       "message_id": "uuid" }                        // final agent text persisted
{ "type": "error",      "code": "agent_error", "message": "…" }       // human-readable failure
```

Ordering guarantees:
- Exactly one `meta` first, then zero+ `tool_start`/`tool_end` and `token` frames
  interleaved, terminated by exactly one `done` **or** one `error`.
- `token` frames are append-only; concatenating all `token.text` in order yields the
  final message content (equal to what `done` persisted).

Error codes: `busy`, `empty_message`, `invalid_model`, `agent_error`,
`upstream_error` (Warcraft Logs failure), `internal`.

## Notes

- Maps directly onto ADK `Runner.run_async` events (partial text → `token`,
  `function_call` → `tool_start`, `function_response` → `tool_end`,
  `is_final_response` → `done`). This is the `cli.py` loop redirected to the socket.
- Connection drop mid-stream: the client surfaces a disconnected state and may retry
  the turn; partial text is not treated as complete (SC-007).
