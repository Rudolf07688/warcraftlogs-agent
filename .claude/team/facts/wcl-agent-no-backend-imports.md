---
id: wcl-agent-no-backend-imports
anchors: [file:wcl_agent/]
by: dev-3 Nils
source: meta/team/dev-3.md L19; meta/sprints/2026-11-04b/board.jsonl #36; meta/sprints/2026-11-02/board.jsonl #53
verified: b9cf9a3 2026-11-05
---
`wcl_agent` never imports `backend`: it runs standalone, and only backend may import
wcl_agent. So OTel instruments for wcl_agent code live in wcl_agent (`app.cache.requests`
in `cache.py`, the GenAI spans in `generation.py`; OTel API only, no-ops without a provider),
and shared helpers move into wcl_agent (`neutralise` in report_tools, `DIFFICULTY_NAMES`
in `wcl_agent/game`).
