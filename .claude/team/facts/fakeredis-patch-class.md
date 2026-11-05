---
id: fakeredis-patch-class
anchors: [sym:backend/tests/conftest.py::fake_redis]
by: dev-2 Tomas
source: meta/team/dev-2.md L20; meta/sprints/2026-11-01/board.jsonl #143
verified: b9cf9a3 2026-11-05
---
The `fake_redis` fixture builds a new `fakeredis.FakeAsyncRedis` on one `FakeServer` for each
`_make_redis` call, and the probe it returns is yet another instance. A test that counts Redis
reads (a "still shared" test, for example) must patch the methods on the `FakeAsyncRedis` class, not on
one instance. Otherwise it counts nothing and fails in every clean run.
