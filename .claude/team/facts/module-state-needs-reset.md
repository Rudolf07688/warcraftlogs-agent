---
id: module-state-needs-reset
anchors: [sym:backend/app/services/raw_fetch_reads.py::breaker, sym:backend/app/services/fetch_persistence.py::_tombstones, sym:wcl_agent/llm/model_retry.py::_limited_until]
by: dev-2 Tomas
source: meta/team/dev-2.md L13
verified: b9cf9a3 2026-11-05
---
Some state is process-wide module state and survives from one test to the next: the raw-store breaker
(`raw_fetch_reads.breaker`), the report tombstones (`fetch_persistence._tombstones`) and the
model retry memory (`model_retry._limited_until`). A test that trips them needs a reset.
When `conftest.py` isn't yours, add an autouse fixture in your own test module, as
`test_raw_store_probe.py` does.
