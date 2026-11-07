---
id: wcl-player-actors-include-bystanders
anchors: [sym:backend/app/services/raid_summary.py::_actor_rows, file:wcl_agent/tools/report_tools.py]
by: dev-3 Nils
verified: 20d4197 2026-11-07
---
A report's masterData.actors(type: "Player") lists everyone the log saw, including bystanders
WCL gives subType "Unknown" (live: a <=30-player Heroic raid had 100+). Who raided is the union
of the fights' friendlyPlayers (actor ids); the raid summary keeps only those actors (072-fix).
