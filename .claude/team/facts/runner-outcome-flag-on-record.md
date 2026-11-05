---
id: runner-outcome-flag-on-record
anchors: [sym:backend/app/agent_runner.py::_run_turn, file:backend/app/api/ws.py]
by: dev-3 Nils
source: meta/team/dev-3.md L15; meta/sprints/2026-11-01b/board.jsonl #83
verified: b9cf9a3 2026-11-05
---
To tell `ws.py` about a turn's outcome, put a flag on the yielded record, never match on its
text. The closing no-answer token carries `"empty": True`; `ws.py` pops it before sending
(the wire frame is unchanged) and then skips the KB offer, the title and follow-up
suggestions.
