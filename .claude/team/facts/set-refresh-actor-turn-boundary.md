---
id: set-refresh-actor-turn-boundary
anchors: [sym:wcl_agent/cache/cache.py::set_refresh_actor, sym:wcl_agent/cache/cache.py::abandon_turn]
by: dev-2 Tomas
source: meta/sprints/2026-11-01/board.jsonl #41; meta/sprints/2026-11-02/board.jsonl #33
verified: b9cf9a3 2026-11-05
---
`ws._handle_turn` calls `set_refresh_actor(user)` at turn start and `set_refresh_actor(None)` at the end.
These calls are also the chat-turn boundary: they open a `_Turn` holder that
`note_external_call` marks, and on close they count the turn, as local when it made no
network WCL call. `abandon_turn` closes a turn without counting it. Hook per-turn WCL
accounting here, not in `ws.py`.
