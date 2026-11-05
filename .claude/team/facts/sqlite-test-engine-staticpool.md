---
id: sqlite-test-engine-staticpool
anchors: [sym:backend/tests/conftest.py::engine]
by: dev-1 Ansel
source: meta/team/dev-1.md L16
verified: b9cf9a3 2026-11-05
---
The SQLite test engine is one in-memory connection (`StaticPool`), and every session in the
test shares it, along with its transaction state. Never poll the DB from the test while a
background task holds a transaction open. Await or drain the task first, then read.
