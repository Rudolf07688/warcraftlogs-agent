---
id: contextvar-mutable-holder
anchors: [sym:wcl_agent/cache/cache.py::_Load, sym:wcl_agent/cache/cache.py::mark_unshareable]
by: dev-2 Tomas
source: meta/team/dev-2.md L17
verified: b9cf9a3 2026-11-05
---
A per-call flag that must cross `asyncio.gather` or threads is a ContextVar holding a
mutable object. It is set at the boundary (`get_or_load` sets `_current_load`) and marked
deep inside (`mark_unshareable`, `note_external_call`). Child tasks run in a copied context:
they can mutate the shared object, but a `ContextVar.set()` made inside them never reaches
the caller.
