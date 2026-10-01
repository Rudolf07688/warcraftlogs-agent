# Contract: REST API

Base path: `/api`. JSON in/out. Async FastAPI handlers. Pydantic request/response
models. Single-user, no auth (v1).

## GET /health

Liveness/readiness.

- **200** → `{ "status": "ok", "db": "ok" }`

## GET /api/models

List selectable model ids (the configured allow-list).

- **200** → `{ "models": ["gemini-3.6-flash", "gemini-3.7-flash"], "default": "gemini-3.6-flash" }`

## GET /api/conversations

List conversations for the sidebar, most-recent-first.

- **200** →
  ```jsonc
  { "conversations": [
      { "id": "uuid", "title": "Hunters on Heroic Ula'tek", "model": "gemini-3.6-flash",
        "created_at": "2026-10-01T12:00:00Z", "updated_at": "2026-10-01T12:05:00Z" }
  ] }
  ```

## POST /api/conversations

Create an empty conversation.

- Body: `{ "model": "gemini-3.6-flash", "title": "optional" }`
- **201** → the conversation object (as above).
- **400** → `{ "error": "invalid_model" }` if model not in allow-list.

## GET /api/conversations/{id}

Fetch one conversation with its full message history (for reopening from sidebar).

- **200** →
  ```jsonc
  { "id": "uuid", "title": "…", "model": "…", "created_at": "…", "updated_at": "…",
    "messages": [
      { "id": "uuid", "role": "user",  "content": "…", "seq": 0, "created_at": "…" },
      { "id": "uuid", "role": "agent", "content": "…", "seq": 1, "created_at": "…" }
    ] }
  ```
- **404** → `{ "error": "not_found" }`

## DELETE /api/conversations/{id}

Delete a conversation and its messages (cascade).

- **204** → no body.
- **404** → `{ "error": "not_found" }`

## Notes

- Sending chat messages is **not** a REST call — it goes over the WebSocket
  (`contracts/websocket.md`). REST covers conversation lifecycle + model listing.
- All response bodies are Pydantic models (constitution IV); errors use a consistent
  `{ "error": "<code>" }` shape with an appropriate status.
