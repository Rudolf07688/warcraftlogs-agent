---
id: raid-summary-tool-keys
anchors: [sym:backend/app/services/raid_summary.py::part_keys, file:wcl_agent/tools/participants.py]
by: dev-3 Nils
verified: 5063145 2026-11-07
---
The Raids page summary (072) finds stored rows by recomputing the exact store keys our tools
send: participants and player-details (fight 0), per-boss Summary tables (kickoff fights) and
get_report_rankings with Rankings/Historical (fight 0 and per boss). A change to a tool's field
text, variable declarations or variable names silently empties that part; test_072 stores rows
from the tools' own fake-client calls, so it fails first.
