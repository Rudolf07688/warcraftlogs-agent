---
id: runner-test-fakes
anchors: [file:backend/app/agent_runner.py, file:backend/tests/test_context_injection.py]
by: dev-3 Nils
source: meta/team/dev-3.md L16; meta/sprints/2026-11-05/board.jsonl #39
verified: b9cf9a3 2026-11-05
---
The `agent_runner` tests feed `SimpleNamespace` events and parts through fake runners
(`test_046_empty_turn`, `test_tool_start_once`, `test_context_injection`, whose strict
`run_async` takes only user_id, session_id, new_message and run_config). Read event
fields with `getattr` and a default, and pass extra `run_async` kwargs only on the paths
that need them (`state_delta` on chat turns only).
