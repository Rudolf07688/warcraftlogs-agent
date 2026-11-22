---
id: wcl-time-window-args
anchors: [sym:wcl_agent/tools/report_tools.py::OPEN_END_MS, sym:wcl_agent/tools/report_tools.py::player_details_query, sym:wcl_agent/tools/report_tools.py::ranked_fight_ids]
by: dev-2 Tomas
verified: 365129b 2026-11-20
---
WCL report fields are picky about window args: events(startTime) with no endTime returns no
events at all (sc-570); playerDetails(fightIDs: null) (sc-573) and rankings(fightIDs: null)
(sc-587) are an Internal server error on some reports; bare playerDetails is a validation error.
Send endTime: OPEN_END_MS (10**12) with any start; ask a whole report's playerDetails as
startTime 0 + OPEN_END_MS (player_details_query) and its rankings with the encounter fight ids
(ranked_fight_ids). A fightIDs filter still bounds an open end.
