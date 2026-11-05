---
id: clock-seam-wall-clock-budgets
anchors: [sym:wcl_agent/llm/model_retry.py::_clock]
by: dev-2 Tomas
source: meta/team/dev-2.md L22; meta/sprints/2026-11-02/board.jsonl #35
verified: b9cf9a3 2026-11-05
---
A wall-clock budget reads a module-level `_clock = time.monotonic` that tests replace
(`model_retry._clock`; the "sleeps" fixture in `test_model_fallback.py` advances it). Never
patch `time.monotonic` globally: asyncio and the libraries read it too.
