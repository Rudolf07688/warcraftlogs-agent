---
id: wcl-time-window-args
anchors: [sym:wcl_agent/tools/report_tools.py::OPEN_END_MS, sym:wcl_agent/tools/report_tools.py::player_details_query]
by: dev-2 Tomas
verified: 365129b 2026-11-20
---
WCL report fields are picky about window args: events(startTime) with no endTime returns no
events at all (sc-570), and playerDetails(fightIDs: null) is an Internal server error on some
reports (sc-573); bare playerDetails is a validation error. Send endTime: OPEN_END_MS (10**12)
with any start, and ask a whole report's playerDetails as startTime 0 + OPEN_END_MS
(player_details_query). A fightIDs filter still bounds an open end.
