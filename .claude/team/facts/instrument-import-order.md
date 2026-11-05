---
id: instrument-import-order
anchors: [sym:backend/app/telemetry/setup.py::instrument]
by: dev-3 Nils
source: meta/team/dev-3.md L21; meta/sprints/2026-11-05/board.jsonl #92
verified: b9cf9a3 2026-11-05
---
wrapt-based instrumentors patch module attributes, but a module that ran `from x import f`
earlier keeps its own binding. So `instrument()` imports `sqlalchemy.ext.asyncio.engine` inside
the function, after `SQLAlchemyInstrumentor`, and points `_create_engine` at
`inspect.unwrap(create_engine)`: one tracer per async engine (sc-474). A module-top import
elsewhere can hide such a bug, so in a test, import after the patch, then mutate.
