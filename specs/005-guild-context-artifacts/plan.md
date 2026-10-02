# Implementation Plan: Personalized Guild Context, Interactive Artifacts & Faster Analysis

**Branch**: `main` (spec dir `005-guild-context-artifacts`) | **Date**: 2026-10-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-guild-context-artifacts/spec.md`

## Summary

Six slices on top of the existing streaming chat app (Phases 1–3 complete). They add
personalization, interactive visuals, and performance to the Warcraft Logs analyst:

1. **US1 Profile & guild context (P1)** — a single global profile (self character, friend
   characters, one main guild). Each turn, a compact, non-persisted **context preamble** is
   prepended to the model input so Barnaby resolves "me/us/our guild" to the saved identities and
   scopes answers to them **when the phrasing is self/friend/guild-referential** (agent-inferred,
   no UI toggle — per clarification).
2. **US2 Interactive artifacts (P1)** — a new agent tool `create_chart` lets Barnaby declare a
   chart from data he already has; the backend turns that **chart spec** into a Plotly figure JSON,
   emits it as an `artifact` WS frame, and persists the spec so it re-renders on reload. The
   frontend renders it with `react-plotly.js` (hover/zoom). Charts/plots are the only artifact kind
   this feature ships; the frame is designed extensibly.
3. **US3 Math/LaTeX (P1)** — the streaming renderer learns `remark-math` + `rehype-katex` (KaTeX)
   so `$…$`/`$$…$$` typeset cleanly during and after streaming; the PDF renders math legibly.
4. **US4 Result caching (P2)** — an **in-process, two-tier TTL cache** at the single `WCLClient.query`
   chokepoint (immutable report-scoped lookups ~24h, volatile leaderboard ~1h) cuts latency and
   WCL API-point spend on repeat lookups. (Existing in-turn parallelism via ADK worker threads is
   retained; no new workflow/subagent machinery — YAGNI.)
5. **US5 Per-message PDF (P2)** — a per-message "Download report" control exports one agent reply
   plus its originating question and its charts/graphs, reusing the existing ReportLab pipeline.
6. **US6 Auto-fetched spec guide (P2)** — locking in a character/guild starts a **non-blocking
   background task** that resolves the character's active spec from WCL and compiles a concise
   guide via the web-search-capable guide model (Gemini), persisted on the profile row and folded
   into the US1 preamble.

Technical approach reuses the established backbone: the `agent_runner.stream_response` generator and
`ws._handle_tool_end` capture path (artifacts ride alongside the existing raid/graph capture);
`render_report_pdf` + the matplotlib `_graph_image` helper (per-message PDF and artifact-in-PDF
rendering share one chart spec); `stream_response` over a disposable session (guide generation,
mirroring the greeting primer); additive, idempotent `create_all`/`ALTER … IF NOT EXISTS`
migrations in `lifespan`. One **chart spec** is the single source of truth, rendered to Plotly on
the frontend and to matplotlib in the PDF (DRY). Frontend grows two libraries: `react-plotly.js`
(+`plotly.js-dist-min`) and `katex` (+`remark-math`/`rehype-katex`).

## Technical Context

**Language/Version**: Python **3.14** (backend, per `.python-version` + constitution); TypeScript 5.5;
React 19 (current).

**Primary Dependencies**:
- Backend (existing): FastAPI + asyncio, google-adk (Gemini/Anthropic via Vertex), SQLAlchemy[asyncio]
  + asyncpg, Pydantic / pydantic-settings, ReportLab + matplotlib (PDF), `requests` (WCL client).
- Backend (**new**): **plotly** (server-side figure JSON for artifacts; spec→Plotly conversion). No
  `kaleido`/static-image dep — PDF reuses matplotlib from the same chart spec.
- Frontend (existing): React 19 + Vite 5, Tailwind v4, shadcn/ui, motion, **streamdown**,
  use-stick-to-bottom, @tsparticles, react-icons/gi.
- Frontend (**new**): **react-plotly.js** + **plotly.js-dist-min** (interactive charts); **katex** +
  **remark-math** + **rehype-katex** (math rendering layered onto Streamdown's plugin pipeline).

**Storage**: PostgreSQL (unchanged) + **three additive tables** (`user_characters`, `guild_profile`,
`artifacts`) and one additive column (`captured_graphs`/artifact linkage via `message_seq`, already
present). The WCL result cache is **in-process** (not persisted). All migrations are additive and
idempotent in `lifespan` (create_all + `ALTER … ADD COLUMN IF NOT EXISTS`), consistent with prior phases.

**Testing**: pytest + pytest-asyncio + httpx (backend), SQLite-backed models in tests. New tests:
`test_profile`, `test_profile_context`, `test_wcl_cache`, `test_charts`, `test_artifacts`,
`test_message_report`, `test_guide` (+ extend `test_api`, `test_pdf_report`). Frontend UI
(profile editor, Plotly artifact, math, per-message PDF) is verified via `quickstart.md` manual steps.

**Target Platform**: Linux server (containerized) + modern evergreen browsers.

**Project Type**: Web application — `backend/` (FastAPI), `frontend/` (React/Vite), `wcl_agent/`
(ADK agent package, also used by the CLI).

**Performance Goals**: cached repeat lookups spend **zero** additional WCL API points and return
without a network round-trip (SC-005); profile save returns < ~1 s with the guide fetched in the
background (SC-007); artifact rendering stays interactive (hover/zoom) and never blocks streaming;
math typesets without reflow jitter.

**Constraints**: never block the asyncio event loop — the guide task is a fire-and-forget
`asyncio.create_task`, WCL/LLM work stays on ADK worker threads / `to_thread`; the in-process cache is
plain in-memory (no I/O); artifacts and math must be **streaming-safe** (artifacts emit only on a
complete `tool_end`; KaTeX only typesets complete delimiters); keep the WebSocket transport and all
existing frames; `wcl_agent` stays standalone (no backend/DB import) — the cache lives in `wcl_agent`
with an in-memory default, and `create_chart` returns a plain spec with no plotly dependency.

**Scale/Scope**: single global profile (default tenant, no auth); single process, low concurrency;
a handful of friend characters; charts with a few series and up to a few hundred points; guide text a
few KB per character.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Strict DRY & Reuse-First | PASS — one **chart spec** rendered by both Plotly (frontend) and matplotlib (PDF, reusing `_graph_image`'s approach); artifacts ride the existing `_handle_tool_end` capture backbone and the `CapturedGraph` persistence pattern; guide generation reuses `stream_response` over a disposable session (as the greeting primer does); per-message PDF reuses `render_report_pdf`; caching sits at the single `WCLClient.query` chokepoint; profile context built once in a shared service. |
| II. Methodical, Step-Wise Delivery | PASS — six independently shippable, independently testable slices; within US2, the backend chart spec + persistence is verifiable before the frontend Plotly component; US6 layers purely on US1. |
| III. Simplicity First (YAGNI) — NON-NEGOTIABLE | **PASS WITH JUSTIFICATION** — `plotly.js` is a large dependency but is the user's explicit goal (interactive plots), recorded in Complexity Tracking; mitigated by `plotly.js-dist-min` and lazy-loading the artifact component. The cache is kept **in-process** (no DB/driver churn), profile context is a **preamble** (no session-state templating or extra per-turn tool round-trip), and **no new workflow/subagent framework** is added for US4 (existing ADK-thread parallelism + caching meet the speed goal). |
| IV. Typed Data Contracts | PASS — new Pydantic: `CharacterIn/CharacterOut`, `GuildIn/GuildOut`, `ProfileOut`, `ChartSpec`, `ArtifactOut`, `ArtifactFrame`; mirrored in the frontend `Frame`/`types` unions. Tool boundaries validate (`create_chart` parses `series_json` like `run_wcl_graphql` parses `variables_json`). |
| V. Async Python Backend | PASS — guide task is non-blocking (`asyncio.create_task`), its WCL/LLM work off the event loop; the in-process cache does no I/O; artifact persistence rides the existing async session in `_handle_tool_end`; per-message PDF uses `asyncio.to_thread` like the existing export. |
| VI. Repo Awareness via GitNexus | PASS (process) — run `gitnexus_impact` before editing `stream_response`, `_handle_turn`, `_handle_tool_end`, `build_agent`/`INSTRUCTION`, `WCLClient.query`, `render_report_pdf`, and `main.lifespan`; `gitnexus_detect_changes` before commit. |

**Result**: PASS (Phase 0 gate) — Principle III justified in Complexity Tracking. Re-checked post-design (below) — still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/005-guild-context-artifacts/
├── plan.md              # This file
├── research.md          # Phase 0 output (R1–R8 decisions)
├── data-model.md        # Phase 1 output (entities, tables, migrations)
├── quickstart.md        # Phase 1 output (manual verification per story)
├── contracts/
│   ├── rest.md          # profile CRUD, per-message report, conversation artifacts
│   ├── websocket.md     # new `artifact` frame
│   ├── agent-tools.md   # `create_chart` tool + chart spec + INSTRUCTION additions
│   └── caching.md       # WCLClient.query cache contract (keys, tiers, behavior)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
wcl_agent/
├── tools.py            # [edit] + create_chart tool (returns a validated ChartSpec dict; no plotly dep)
├── wcl_client.py       # [edit] add in-process two-tier TTL cache around WCLClient.query (keyed by query+variables)
├── cache.py            # [new] TTLCache (LRU+expiry), key hashing, tier classifier, env-tunable TTLs
└── agent.py            # [edit] INSTRUCTION: use the KNOWN PLAYER CONTEXT block + create_chart guidance; add create_chart to TOOLS

backend/
├── app/
│   ├── api/
│   │   ├── profile.py      # [new] GET /api/profile; PUT self; POST/DELETE friend; PUT/DELETE guild
│   │   ├── reports.py      # [edit] + GET /api/conversations/{id}/messages/{message_id}/report.pdf
│   │   ├── conversations.py# [edit] include persisted artifacts in ConversationDetail
│   │   └── ws.py           # [edit] on create_chart tool_end: build+persist artifact, emit ArtifactFrame; assign message_seq at turn end
│   ├── services/
│   │   ├── profile_context.py # [new] build the compact per-turn context preamble from the Profile
│   │   ├── charts.py          # [new] chart_spec→Plotly figure JSON; chart_spec→matplotlib Image (PDF)
│   │   ├── guide.py           # [new] resolve active spec (WCL) + generate guide (guide model) + persist
│   │   ├── artifacts.py       # [new] capture_artifact_from_tool(create_chart result)
│   │   └── pdf_report.py      # [edit] render chart-spec artifacts (matplotlib) + math-aware inline
│   ├── db/
│   │   ├── models.py          # [new] UserCharacter, GuildProfile, Artifact (+ existing)
│   │   └── repository.py      # [edit] profile CRUD; artifact add/list; assign message_seq to turn captures
│   ├── agent_runner.py        # [edit] accept an optional context_preamble prepended to the model message only
│   ├── schemas.py             # [edit] + CharacterIn/Out, GuildIn/Out, ProfileOut, ChartSpec, ArtifactOut, ArtifactFrame
│   ├── config.py              # [edit] + wcl_guide_model (web-search-capable Gemini); cache TTL env (optional)
│   └── main.py                # [edit] create new tables; install cache config; mount profile router
└── tests/                     # [new] test_profile, test_profile_context, test_wcl_cache, test_charts,
                               #       test_artifacts, test_message_report, test_guide  [edit] test_api, test_pdf_report

frontend/
├── package.json            # [edit] + react-plotly.js, plotly.js-dist-min, katex, remark-math, rehype-katex
├── src/
│   ├── components/
│   │   ├── ProfilePanel.tsx    # [new] edit self/friends/guild; shows guide status
│   │   ├── PlotlyArtifact.tsx  # [new] lazy-loaded react-plotly.js wrapper (reduced-motion aware)
│   │   ├── StreamMarkdown.tsx  # [edit] add remark-math + rehype-katex to the Streamdown pipeline
│   │   ├── MessageList.tsx     # [edit] render per-message artifacts + per-message "Download report" button
│   │   └── Sidebar.tsx         # [edit] entry point to open the Profile panel
│   ├── api/
│   │   ├── restClient.ts       # [edit] profile CRUD; downloadMessageReport(convId, messageId)
│   │   └── wsClient.ts         # [edit] + artifact frame in the Frame union
│   ├── types.ts                # [edit] + Character, Guild, Profile, ChartArtifact; Message.artifacts
│   ├── App.tsx                 # [edit] load profile; accumulate per-turn artifacts; attach on done; wire profile panel
│   └── index.css / styles.css  # [edit] KaTeX import + artifact/profile styling tokens
```

**Structure Decision**: Existing three-package layout retained. The WCL cache lives in `wcl_agent`
(shared by the CLI and the backend, no backend/DB coupling). Backend changes are additive and ride
existing backbones (`stream_response`, `_handle_tool_end`, `render_report_pdf`, `lifespan`
migrations). Backend slices (US1 backend, US4 cache, US5 endpoint, US6 guide) are independent of the
frontend slices (US2 Plotly, US3 math, profile UI) and can proceed in parallel.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **`plotly.js` frontend dependency** (`react-plotly.js` + `plotly.js-dist-min`, large bundle) | User's explicit goal: interactive, hoverable/zoomable charts in chat (US2; todo "pass the json to the js plotly library"). | A static image (matplotlib PNG) is not interactive and fails US2's hover/zoom acceptance. Risk contained by `plotly.js-dist-min` and lazy-loading `PlotlyArtifact` only when a message has artifacts. |
| **`plotly` backend dependency** | Produce the figure JSON (data+layout) from the agent's chart spec on the server (keeps the frontend a thin renderer; keeps figure construction testable in Python). | Hand-building Plotly JSON by string is brittle and untyped; building it client-side would duplicate chart logic and couple the agent's intent to the UI. No `kaleido` is added — PDF reuses matplotlib from the same spec. |
| **New `user_characters` / `guild_profile` / `artifacts` tables** | US1 needs persisted identities + per-character guide; US2 needs artifacts to survive reload (FR-011). | Stuffing profile into existing tables or re-deriving charts on reload is a false economy; these mirror the additive `tracked_raids`/`captured_graphs` pattern and are created idempotently in `lifespan`. |
| **In-process cache instead of DB-persistent** (deviates from an earlier spec wording) | Satisfies every caching FR and SC-005 (no extra API points, faster repeats) with zero I/O and no new driver, at single-process scale. | A Postgres-backed cache needs sync DB access from the ADK worker thread (second driver or a cross-thread `run_coroutine_threadsafe` bridge) — real complexity for marginal cross-restart benefit (YAGNI). The spec assumption was updated to match; the cache sits behind an interface so a persistent backend can slot in later. |

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1 (data-model, contracts): **still PASS.** One chart spec is the single
source of truth for both renderers; artifacts/guides/profile reuse existing backbones and the additive
idempotent-migration pattern; the agent package stays standalone; all new boundary data is typed; no
blocking work is added to the event loop. Principle III is satisfied via the Complexity Tracking
justification for the user-directed interactive-plot stack, with the cache and profile-context designs
chosen for simplicity.
