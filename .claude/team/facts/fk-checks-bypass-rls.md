---
id: fk-checks-bypass-rls
anchors: [sym:backend/app/db/models.py::KbChatChunk, sym:backend/app/db/models.py::Message, comp:postgres]
by: dev-1 Ansel
source: meta/team/dev-1.md L14; meta/sprints/2026-11-01/board.jsonl #34, #44; meta/sprints/2026-11-01b/board.jsonl #57
verified: 03a3982 2026-11-07
---
Postgres foreign-key checks ignore RLS. A tenant-scoped row that references another tenant
table needs a composite FK `(x_id, tenant_id) -> (id, tenant_id)` plus `UNIQUE(id,
tenant_id)` on the target, as `kb_chat_chunks -> conversations` has (0019). Without one, a
workspace's insert can name another workspace's row. `messages.conversation_id` is still a
plain FK (backlog); the callers check ownership first.
