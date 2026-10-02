# Implementation Plan: Raid Sourcing, Tracking & Report UX

**Branch**: `main` (spec dir `004-raid-sourcing-ux`) | **Date**: 2026-10-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-raid-sourcing-ux/spec.md`

## Summary

Six slices on top of the existing streaming chat app (Phases 1–2 complete). Five are the
functional Phase-3 items; the sixth is a re-scoped, **app-wide high-fantasy UX overhaul**
(the `react-modern-ui` skill, full adoption — see Clarifications in the spec):

1. **US1 Source links (P1)** — Barnaby cites the Warcraft Logs URL behind data he uses, built
   from identifiers the tools already return; links open in a new tab.
2. **US2 Accurate raid list (P1)** — the sidebar shows each raid's own date/time + boss(es),
   de-duplicated with a race-safe upsert.
3. **US3 PDF fidelity (P2)** — the markdown→PDF converter learns tables, numbered lists, and
   long-token wrapping.
4. **US4 Boss focus (P2)** — a report's distinct bosses are forwarded to the UI as checkboxes
   that fold the chosen bosses into the next prompt.
5. **US5 New-chat greeting (P3)** — a Barnaby greeting generated once at startup, cached per
   session, shown instantly on a new chat.
6. **US6 High-fantasy polish (P1, app-wide)** — one fixed curated theme on CSS tokens, smooth
   "inscribed" token streaming (Streamdown + adaptive buffer + ink-in + stick-to-bottom),
   tool calls as animated "spellcasting" cards (summoning → casting → resolved/fizzled), and
   subtle ambient effects, with hard reduced-motion and ~60 fps constraints.

Technical approach: US1–US5 largely as previously planned (prompt edit + markdown link render;
race-safe `ON CONFLICT` upsert + `encounters` JSON column + sidebar display swap; extended
ReportLab table/list rendering; an `encounters` WS frame + picker; a cached greeting helper).
US6 is a **frontend stack migration + visual layer**: upgrade React 18→19, adopt Tailwind v4 +
shadcn/ui + `motion` + `streamdown` + `use-stick-to-bottom` + `@tsparticles` + `react-icons/gi`;
replace the Phase-2 background toggle with a single fixed theme (retaining the existing
background images as its backdrop); keep the existing **WebSocket** transport and drive the
spellcasting/streaming UI from the current frames (adding `summary`/`ms` to `tool_end` and an
optional `tool_progress` frame). The migration is sequenced as **Foundational** because the
whole frontend (including US1–US5's new UI) is then built on the new stack.

## Technical Context

**Language/Version**: Python **3.14** (backend, per `.python-version` + constitution);
TypeScript 5.5; **React 19** (upgraded from 18.3 as part of US6).

**Primary Dependencies**:
- Backend (unchanged): FastAPI + asyncio, google-adk (Gemini/Anthropic via Vertex),
  SQLAlchemy[asyncio] + asyncpg, Pydantic / pydantic-settings, ReportLab + matplotlib (PDF).
- Frontend (**grows substantially** for US6): React 19 + Vite 5; **Tailwind CSS v4**
  (`@tailwindcss/vite`); **shadcn/ui** (CSS-first, OKLCH tokens); **motion** (`motion/react`);
  **streamdown** (streaming-safe markdown, replaces `react-markdown`); **use-stick-to-bottom**;
  **@tsparticles/react** + **@tsparticles/slim**; **react-icons/gi** (game-icons.net, CC BY 3.0);
  `remark-gfm` retained via Streamdown; a `rehype` word-span plugin for ink-in.

**Storage**: PostgreSQL (unchanged) + **one additive column** `tracked_raids.encounters` (JSON);
in-process `app.state` greeting cache (not persisted); browser `localStorage` for sidebar width
(retained). The Phase-2 background-choice preference is **removed** (single fixed theme).

**Testing**: pytest + pytest-asyncio + httpx (backend). Frontend has no test harness; UI slices
(US1, US4 UI, US5 UI, and all of US6) are verified via `quickstart.md` manual steps, incl. a
reduced-motion pass and a frame-rate spot check.

**Target Platform**: Linux server (containerized) + modern evergreen browsers (View Transitions
and `@property` used progressively; graceful fallback where absent).

**Project Type**: Web application — `backend/` (FastAPI), `frontend/` (React/Vite),
`wcl_agent/` (ADK agent package).

**Performance Goals**: source links add zero latency (prompt-only); greeting served from cache
< ~1s on 2nd+ new chats; **streaming sustains ~60 fps** with token smoothing and per-word CSS
(not JS) animation; particles capped (30–60) and paused when `document.hidden`.

**Constraints**: never block the asyncio event loop (PDF/greeting already offloaded); **keep the
WebSocket transport** (no SSE migration); preserve all existing frames; **honor reduced-motion**
(disable blur/rotation/particles); maintain chat-text legibility over the retained background
images; IP-safe styling only (no Blizzard assets; game-icons CC BY credit); dedup stays keyed on
`report_code`.

**Scale/Scope**: single-guild, low concurrency; tool outputs up to a few MB; reports with up to
~15–20 distinct encounters; thousands of streamed word-spans per long answer (CSS-only animation).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Strict DRY & Reuse-First | PASS — one theme-token source, one `spells` registry, one `useSmoothText` buffer, one streaming renderer; reuse the existing WS `Frame` union, Pydantic frame schemas, `_handle_tool_end` capture backbone, `upsert_tracked_raid`, `RaidOut`/`Raid` contracts, and the `to_thread` PDF offload. |
| II. Methodical, Step-Wise Delivery | PASS — US1–US5 remain independently shippable; US6's **stack migration is isolated as a Foundational step** verified on its own (app builds & streams on React 19/Tailwind) before the visual layer is added incrementally (tokens → streaming → spell cards → ambient). |
| III. Simplicity First (YAGNI) — NON-NEGOTIABLE | **PASS WITH JUSTIFICATION** — the full-skill stack (React major upgrade + Tailwind v4 + shadcn/ui + motion + tsparticles) is a large, explicitly user-directed product requirement ("full adoption"), recorded in Complexity Tracking. Mitigated by: one fixed theme (no multi-theme engine), keeping the existing transport, and CSS-only per-word animation. The `encounters` JSON column is the only other tracked item. |
| IV. Typed Data Contracts | PASS — new `EncounterOut`, `EncountersFrame`, `GreetingResponse`; `ToolEndFrame` gains typed `summary`/`ms`; optional typed `ToolProgressFrame`; all mirrored in the frontend `Frame`/`types` unions. |
| V. Async Python Backend | PASS — US6 is frontend-heavy; the only backend touch (tool `summary`/`ms`, optional `tool_progress`) rides the existing async generator; greeting primes off the event loop; no blocking added. |
| VI. Repo Awareness via GitNexus | PASS (process) — run `gitnexus_impact` before editing `_handle_tool_end`, `stream_response`, `upsert_tracked_raid`, `render_report_pdf`, and the agent `INSTRUCTION`; `gitnexus_detect_changes` before commit. (Frontend TS may be outside the index; apply the same care manually.) |

**Result**: PASS (Phase 0 gate) — with Principle III justified in Complexity Tracking.
Re-checked post-design (below) — still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/004-raid-sourcing-ux/
├── plan.md              # This file
├── research.md          # Phase 0 output (incl. US6 stack decisions R6–R9)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── websocket.md     # encounters frame + tool_end summary/ms + optional tool_progress
│   ├── rest.md          # greeting endpoint + RaidOut.encounters
│   ├── agent-output.md  # WCL source-link format + PDF rendering contract
│   └── ui-polish.md     # US6: stream protocol→UI mapping, spell registry, theme tokens, a11y
└── tasks.md             # /speckit-tasks (regenerated to include US6)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── api/
│   │   ├── ws.py             # [edit] emit EncountersFrame; add summary/ms to tool_end; optional tool_progress
│   │   ├── raids.py          # [edit] RaidOut carries encounters
│   │   ├── reports.py        # [edit] include user questions as context (US3)
│   │   └── greeting.py       # [new] GET /api/greeting?model=
│   ├── services/
│   │   ├── raids.py          # [edit] capture distinct encounters onto the raid
│   │   ├── encounters.py     # [new] encounters_from_tool(get_report_fights result)
│   │   ├── tool_summary.py   # [new] short human-readable summary of a tool result (US6/FR-032)
│   │   └── pdf_report.py     # [edit] tables, numbered/mixed lists, long-token wrap
│   ├── db/{models.py,repository.py}  # [edit] TrackedRaid.encounters; race-safe upsert; persist/read encounters
│   ├── greeting.py           # [new] get_greeting(app, model) cache + generation
│   ├── agent_runner.py       # [edit] time each tool call; surface summary/ms in tool_end record
│   ├── schemas.py            # [edit] + EncounterOut/EncountersFrame/GreetingResponse; ToolEndFrame.summary/ms; ToolProgressFrame
│   └── main.py               # [edit] prime greeting cache; mount greeting router; add encounters column
└── tests/                    # [new/edit] test_encounters, test_raids, test_pdf_report, test_greeting, test_api (+tool_end summary)

frontend/
├── package.json              # [edit] React 19; add tailwindcss@4, @tailwindcss/vite, motion, streamdown,
│                             #        use-stick-to-bottom, @tsparticles/react, @tsparticles/slim, react-icons; shadcn deps
├── vite.config.ts            # [edit] add @tailwindcss/vite plugin
├── tsconfig*.json            # [edit] React 19 types
├── components.json           # [new] shadcn/ui config
├── src/
│   ├── index.css             # [new] Tailwind v4 entry + @theme tokens + single fixed theme + grain/vignette + keyframes
│   ├── styles.css            # [edit→migrate] fold existing rules into token-based styles (or retire)
│   ├── lib/
│   │   ├── utils.ts          # [new] shadcn cn() helper
│   │   ├── spells.ts         # [new] per-tool SPELLS registry (icon/hue/verb/flavor) + DEFAULT_SPELL
│   │   └── rehypeWordSpans.ts# [new] wrap words in .ink spans for ink-in reveal
│   ├── hooks/useSmoothText.ts# [new] adaptive token-smoothing buffer
│   ├── components/
│   │   ├── StreamMarkdown.tsx# [new] Streamdown + rehypeWordSpans + new-tab link render (replaces Markdown.tsx; serves US1)
│   │   ├── SpellCard.tsx     # [new] summoning/casting/resolved/fizzled card
│   │   ├── CastBar.tsx       # [new] indeterminate→determinate cast bar
│   │   ├── RuneCircle.tsx    # [new] pure-SVG rotating rune circle
│   │   ├── Ambient.tsx       # [new] drifting gradients + capped theme particles (reduced-motion aware)
│   │   ├── MessageList.tsx   # [edit] stick-to-bottom, ember caret, completion flourish, spell cards, EncounterPicker
│   │   ├── EncounterPicker.tsx # [new] boss checkboxes (US4), themed
│   │   ├── Sidebar.tsx       # [edit] raid date/time + boss(es) (US2), themed
│   │   ├── Markdown.tsx      # [remove] superseded by StreamMarkdown
│   │   └── BackgroundToggle.tsx # [remove] single fixed theme (FR-027)
│   ├── config.ts             # [edit] drop background registry; keep a single fixed background constant
│   ├── uiPrefs.ts            # [edit] drop background pref; keep sidebar width
│   ├── types.ts              # [edit] Encounter, Raid.encounters, tool-call/turn spell state, tool_end summary/ms
│   ├── api/{wsClient.ts,restClient.ts} # [edit] encounters + tool_progress + tool_end summary/ms frames; getGreeting()
│   └── App.tsx               # [edit] fixed theme; drive spell-card state from frames; greeting on newChat; remove bg toggle wiring
```

**Structure Decision**: Existing three-package layout retained. US6 adds a frontend `lib/` and
`hooks/` folder and several presentational components, and migrates the build to Tailwind v4 +
React 19. Backend changes for US6 are minimal and additive (typed `tool_end` fields + optional
`tool_progress`). **Backend slices (US2/US3/US4-capture/US5-backend) are independent of the
frontend migration** and can proceed in parallel with it.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **Full frontend stack migration** (React 18→19, Tailwind v4, shadcn/ui, motion, streamdown, use-stick-to-bottom, @tsparticles, react-icons/gi) | User explicitly directed **full adoption** of the `react-modern-ui` polish as a headline, app-wide outcome (spec Clarifications, US6). Premium streaming/animation UX is the stated product goal for this feature. | A CSS-only / curated-subset approach was offered and **declined** by the user. Streamdown (safe streaming markdown), motion (spell cards), and stick-to-bottom each solve a real problem the hand-rolled approach does poorly; Tailwind v4 + shadcn give the token system the skill is built around. Risk is contained by isolating the migration as a verified Foundational step and shipping **one** fixed theme (not a theme engine). |
| **React major upgrade (18→19)** as part of the above | The skill's libraries and patterns target React 19.1+; staying on 18 would fight the ecosystem. | Pinning to 18 risks peer-dep conflicts with current `motion`/shadcn/streamdown versions; the upgrade is done once, up front, and verified before feature UI is built on it. |
| New `tracked_raids.encounters` JSON column | Serves US2 (boss display) and US4 (focus checkboxes) from one `get_report_fights` payload without a second WCL call. | A normalized `TrackedEncounter` table is over-normalized for a short, read-mostly inline list (YAGNI); re-deriving on demand costs an extra WCL call. Mirrors `captured_graphs.graph_json`; added idempotently in lifespan. |
| Keep WebSocket transport (vs skill's SSE) | The app already streams correctly over WS and the frames map 1:1 to the skill's event taxonomy; migrating would be pure rework. | SSE-over-POST rewrite of `ws.py`/`agent_runner`/frontend socket client delivers no functional benefit and violates Simplicity-First. |

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1 (data-model, contracts, ui-polish): **still PASS.** The design keeps a
single source of truth for theme tokens, spells, and the streaming renderer; adds only additive,
typed WS fields; keeps the transport and async backbone intact; and confines the large (justified)
complexity to the frontend stack migration, sequenced and verifiable on its own. Principle III is
satisfied via the Complexity Tracking justification for the user-directed full adoption.
