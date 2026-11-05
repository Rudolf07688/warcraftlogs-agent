---
id: stream-response-shared-by-jobs
anchors: [sym:backend/app/agent_runner.py::stream_response, sym:backend/app/agent_runner.py::_run_turn]
by: dev-3 Nils
source: meta/team/dev-3.md L15; meta/sprints/2026-11-01b/board.jsonl #51; meta/sprints/2026-11-05/board.jsonl #39
verified: b9cf9a3 2026-11-05
---
`stream_response` and `_run_turn` serve chat turns AND greeting, guide jobs and evals. Those
jobs run as `USER_ID` (`"local_user"`). Chat-only behaviour keys on `user_id != USER_ID`,
for example the no-answer token and the `app_turns` state_delta. GitNexus rates both
CRITICAL.
