---
id: raid-summary-tool-keys
anchors: [sym:backend/app/services/raid_summary.py::part_keys, file:wcl_agent/tools/participants.py]
by: dev-3 Nils
verified: 77de758 2026-11-20
---
The Raids page summary (072) finds stored rows by recomputing the exact store keys our tools
send: participants and player-details (fight 0), per-boss Summary tables and get_report_rankings
(Rankings/Historical). A change to a tool's field text or variables silently empties that part;
test_072 stores rows from the tools' own fake-client calls, so it fails first. Participants and
player-details keys come from `participants_query` / `player_details_query`: build new shapes
there, and keep the old key as a read-only fallback (`_LEGACY_DETAILS_FIELDS`) for stored rows.
