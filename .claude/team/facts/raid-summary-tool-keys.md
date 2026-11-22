---
id: raid-summary-tool-keys
anchors: [sym:backend/app/services/raid_summary.py::part_keys, file:wcl_agent/tools/participants.py]
by: dev-3 Nils
verified: 90e21c4 2026-11-22
---
The Raids page summary (072) recomputes the exact store keys our tools send: participants,
player-details (fight 0), per-boss Summary tables, get_report_rankings (Rankings/Historical). Whole-report
rankings: every prefix of the newest summary's `ranked_fight_ids` (live reports only grow); only the newest
row's body is read. A changed field or variable silently empties a part; test_072 fails first. Keep old
keys as read-only fallbacks (`_LEGACY_DETAILS_FIELDS`, fightIDs null rankings).
