# Implementation Plan: Chat Follow-ups & UX Enhancements

**Branch**: `003-chat-followups-ux` | **Date**: 2026-10-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-chat-followups-ux/spec.md`

## Summary

Six independent slices on top of the existing streaming chat app: (1) up to three
clickable, agent-predicted follow-up questions per answer; (2) confirmed-concurrent
tool execution with a per-turn shared scratch store so large tool outputs are never
lost or truncated and partial failures degrade gracefully; (3) a CSS fix so response
panels size to content/window instead of a fixed width/height; (4) the "Barnaby"
innkeeper persona (blunt, funny, calls out mistakes); (5) a drag-resizable, width-
persisted side panel; (6) the new `morgan-howell-img-1760.jpg` background as default
with the previous one retained and switchable via configuration.

Technical approach: a new post-turn `suggestions` WebSocket frame produced by a small
structured generation (no in-band stripping of the streamed answer); a filesystem
scratch store keyed by turn + tool-call id for large tool payloads; a responsive
message-width rule; a one-string edit to the single-source agent prompt; and frontend-
only changes (CSS variable + drag handle + `localStorage` prefs + a background config).

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5.5 / React 18 (frontend)

**Primary Dependencies**: FastAPI + asyncio, google-adk (Gemini/Anthropic via Vertex),
SQLAlchemy[asyncio] + asyncpg, Pydantic / pydantic-settings; React 18 + Vite 5 +
react-markdown

**Storage**: PostgreSQL (conversations, messages, raids, ADK sessions) — unchanged;
**new** per-turn filesystem scratch dir (`tempfile`) for large tool outputs; browser
`localStorage` for UI preferences (side-panel width, background choice)

**Testing**: pytest + pytest-asyncio + httpx (backend). Frontend has no test harness;
UI slices verified via quickstart manual steps.

**Target Platform**: Linux server (containerized) + modern evergreen browsers

**Project Type**: Web application (existing `backend/` + `frontend/`)

**Performance Goals**: follow-up generation adds < ~1s and runs after the answer is
delivered (never delays first token or `done` perceptibly); side-panel drag resize
stays smooth (~60fps); concurrent multi-lookup turns finish faster than sequential.

**Constraints**: never block the asyncio event loop (offload blocking work via
`asyncio.to_thread`); preserve existing streaming/token/tool/grounding frame behavior;
maintain chat-text legibility over either background; no secrets committed.

**Scale/Scope**: single-guild usage, low concurrency; tool outputs up to a few MB
(full report tables, graph JSON).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Strict DRY & Reuse-First | PASS — reuse the existing `Frame` union, Pydantic frame schemas, `stream_response` generator, single-source agent prompt, `Settings`/config pattern, and WS `_handle_turn` loop. One new frame type, one new helper, one new scratch module; no duplicated logic. |
| II. Methodical, Step-Wise Delivery | PASS — six independently testable user stories (P1→P3), each shippable alone; MVP is US1. |
| III. Simplicity First (YAGNI) | PASS with one tracked item — the per-turn scratch store adds a component; justified in Complexity Tracking (large WCL payloads). Follow-ups use one small structured call, not a new framework. UI slices are plain CSS/`localStorage`. |
| IV. Typed Data Contracts | PASS — new `SuggestionsFrame` (Pydantic) mirrored in the frontend `Frame` union; suggestions carried as a typed `list[str]`. |
| V. Async Python Backend | PASS — suggestion generation and any blocking tool/model work run async or via `to_thread`; no new sync endpoints. |
| VI. Repo Awareness via GitNexus | PASS (process) — run `gitnexus_impact` before editing `stream_response`, `_handle_turn`, and the agent prompt; `gitnexus_detect_changes` before commit (enforced at implement time). |

**Result**: PASS (Phase 0 gate). Re-checked post-design below — still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/003-chat-followups-ux/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── websocket.md     # New suggestions frame + parallel-tool behavior
│   └── ui-config.md     # Background config + UI preference contracts
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── agent_runner.py      # [edit] emit suggestions; wire scratch store into tool results
│   ├── suggestions.py       # [new] generate_followups(model, question, answer) -> list[str] (≤3)
│   ├── scratch.py           # [new] per-turn filesystem scratch store for large tool outputs
│   ├── schemas.py           # [edit] + SuggestionsFrame
│   ├── config.py            # [edit] + default_background / background settings (if backend-driven)
│   └── api/ws.py            # [edit] forward suggestions frame; ensure partial-failure handling
└── tests/
    ├── test_suggestions.py  # [new] ≤3, relevance-shaped, empty when trivial
    ├── test_parallel_tools.py  # [new] concurrency + full large-output capture + one-fails-others-ok
    └── test_api.py          # [edit] suggestions frame in the WS turn flow

frontend/
├── public/ (or src/assets/)
│   └── morgan-howell-img-1760.jpg  # [new source] move/copy from dist/assets so the build includes it
├── src/
│   ├── App.tsx              # [edit] handle suggestions frame; render suggestion buttons; resize + bg wiring
│   ├── types.ts             # [edit] Message.suggestions?: string[]
│   ├── config.ts            # [new] background options + default (config-driven, togglable)
│   ├── api/wsClient.ts      # [edit] + suggestions to Frame union
│   ├── components/
│   │   ├── MessageList.tsx  # [edit] render FollowUps under the latest agent turn
│   │   ├── FollowUps.tsx    # [new] up to 3 suggestion buttons
│   │   ├── Sidebar.tsx      # [edit] drag handle / resizer
│   │   └── BackgroundToggle.tsx # [new, optional] in-app background switch
│   └── styles.css           # [edit] responsive message width; --sidebar-width; resizer; background + scrim
```

**Structure Decision**: Existing two-package web layout (`backend/` FastAPI + `frontend/`
React/Vite). No new top-level projects. New backend modules (`suggestions.py`,
`scratch.py`) and new frontend components/config files slot into the current structure.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Per-turn filesystem scratch store (`scratch.py`) | WCL tool results (full tables, graph JSON) can be multiple MB; the user explicitly asked for "shared disk space for tool output the agent can pick up when done" so concurrent large outputs are preserved and handed off reliably | Keeping full results only in-memory/in-band risks context bloat and ties result size to in-transit limits; a durable per-turn handoff point is the smallest mechanism that satisfies FR-007/FR-008 and the stated requirement. Scoped to one module + a `tempfile` dir, auto-cleaned per turn — no new service or dependency. |
