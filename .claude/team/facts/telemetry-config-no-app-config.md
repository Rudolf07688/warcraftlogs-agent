---
id: telemetry-config-no-app-config
anchors: [sym:backend/app/telemetry/config.py::load_config, file:backend/app/config.py]
by: dev-3 Nils
source: meta/team/dev-3.md L18; meta/sprints/2026-11-04/board.jsonl #21
verified: b9cf9a3 2026-11-05
---
Importing `backend.app.config` loads ADK and FastAPI, and telemetry has to start before
both. So `backend/app/telemetry/config.py` reads `os.environ` itself (it loads `.env` the
way config.py does and honours `WCL_LOAD_DOTENV`) and must never import
`backend.app.config`. A setting the telemetry bootstrap needs goes into its own env read,
not into `Settings`.
