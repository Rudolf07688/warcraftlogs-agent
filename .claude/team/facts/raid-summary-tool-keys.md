---
id: raid-summary-tool-keys
anchors: [sym:backend/app/services/raid_summary.py::part_keys, file:wcl_agent/tools/participants.py]
by: dev-3 Nils
verified: 8986855 2026-11-20
---
The Raids page summary (072) finds stored rows by recomputing the exact store keys our tools
send: participants and player-details (fight 0), per-boss Summary tables and get_report_rankings
(Rankings/Historical; whole report = `ranked_fight_ids` of the summary). A changed field text or variable
silently empties that part; test_072 stores rows from the tools' fake-client calls, and fails first. Build new shapes in the shared query helpers and keep the
old key as a read-only fallback (`_LEGACY_DETAILS_FIELDS`, fightIDs null rankings) for stored rows.
