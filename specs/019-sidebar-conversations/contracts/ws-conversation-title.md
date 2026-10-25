# WebSocket contract: `conversation_title` frame (feature 019, sc-155)

The frame is sent server → client on `/ws/chat`. It is added to the frames documented
in `specs/001-*/contracts/websocket.md` and its successors.

```json
{
  "type": "conversation_title",
  "conversation_id": "uuid",
  "title": "Wipes on the last boss, last night's raid"
}
```

## When

- At most once per conversation, ever, and only after that conversation's first complete
  agent reply, so always **after** its `done` frame. It may arrive after `suggestions`, or
  interleaved with the next turn's frames.
- Only for conversations whose name was a default ("New chat" or the first-message
  excerpt). It is never sent for explicitly named conversations (raid investigations,
  recent-raid kickoffs, a `POST` with a title), nor for conversations that existed
  before feature 019.
- Never sent when generation fails, times out or is rate-limited. The client sees
  nothing, and the conversation keeps its excerpt title.

## Guarantees

- `title` is plain text, 1–60 characters, on one line, with no surrounding quotes and no
  markdown.
- The title is saved before the frame is sent, so a client that misses the frame (closed
  socket) sees it on the next `GET /api/conversations`.
- The frame never delays `token`, `done` or the next turn, and is never sent as part of a
  turn's error path.

## Client handling

On receipt, call `refreshConversations()`, which refreshes the sidebar list and the
header's pin state. There is no other state change. Unknown frame types are already
ignored by older clients.
