---
id: index-migrations-concurrently
anchors: [file:backend/migrations/versions/, comp:postgres]
by: dev-1 Ansel
source: meta/team/dev-1.md L18
verified: 03a3982 2026-11-07
---
Index migrations run `create_index`/`drop_index` with `postgresql_concurrently=True`
inside `op.get_context().autocommit_block()` (see 0020 and 0021), so they don't lock
`raw_fetches`. Prove each one up, down and up again against the `DATABASE_OWNER_URL` that
`pg.py up <you>` prints (the owner role), not the runtime URL.
