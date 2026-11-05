---
id: boss-summary-shared
anchors: [sym:wcl_agent/tools/report_tools.py::boss_summary, sym:wcl_agent/tools/report_tools.py::get_report_fights, file:backend/app/services/kickoff_prefetch.py]
by: dev-3 Nils
source: meta/sprints/2026-11-02/board.jsonl #3, #20, #64
verified: 32010a6 2026-11-05
---
`get_report_fights` caps the fight list (`_acap`, 60k chars) but returns `last_kill` and
the per-boss summary (`boss_summary`) outside it, with keystone runs excluded, so "the last
boss kill" survives long nights. `kickoff_prefetch` imports `boss_summary` to pick the same
fights, so keep its signature and keys (`last_kill_fight_id`, `last_pull_fight_id`) stable.
