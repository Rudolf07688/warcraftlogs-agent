# Phase 0 Research: Raid Sourcing, Tracking & Report UX

All five slices build on existing, read code. No open `NEEDS CLARIFICATION` remained after
inspecting the current implementation; the decisions below record the chosen approach,
rationale, and the simpler/heavier alternatives rejected.

---

## R1 — Warcraft Logs source links (US1)

**Decision**: Prompt-driven citation. Add a `SOURCE LINKS` section to the single-source
`INSTRUCTION` in `wcl_agent/agent.py` instructing Barnaby to cite the Warcraft Logs URL
behind any data he uses, as a markdown link, built from identifiers he already holds:

```
https://www.warcraftlogs.com/reports/<report_code>#fight=<fight_id>&type=<metric>&source=<source_id>
```

Rules the prompt encodes: link the report when report-level; append `#fight=<id>` when the
answer concerns a specific pull; add `&source=<source_id>&type=<dps|hps|healing|damage-taken>`
when it's about a specific player/metric; emit one link per distinct source; **never**
fabricate a WCL link for web-search or general-knowledge content (FR-005). Frontend: give
`react-markdown` (in `frontend/src/components/Markdown.tsx`) a custom `a` renderer that adds
`target="_blank" rel="noopener noreferrer"` (FR-003).

**Rationale**: The `report_code`, `fight_id`, and `source_id` already flow to the model through
every report tool (`wcl_agent/report_tools.py`) and the fight list; the model is the only
component that knows *which* fight/source a given sentence was sourced from, so it is the
correct place to emit the link. Prompt + render reuses existing machinery (DRY) and adds zero
latency. The `#fight=&type=&source=` fragment is the real WCL web URL shape, so links resolve.

**Alternatives rejected**:
- *Backend post-processing to inject links* — brittle; the backend can't reliably know which
  claim maps to which fight/source, and it would duplicate knowledge the model already has.
- *A structured `citations` frame rendered as a separate panel* — YAGNI; inline markdown links
  sit exactly where the claim is and need no new transport.

---

## R2 — De-duplicated raid list with date/time + boss (US2)

**Decision**: Three coordinated fixes.
1. **Display the raid's own time, not last-asked.** `TrackedRaid.report_started_at` already
   stores a full UTC timestamp (set in `services/raids.py::_build_label` from
   `start_time_ms`). Change `frontend/src/components/Sidebar.tsx` to render
   `report_started_at` (date **and** time) with a date-only fallback, instead of
   `last_asked_at`. Keep list ordering by `last_asked_at desc` (recency of interest).
2. **Race-safe upsert.** Replace the check-then-insert in `repository.upsert_tracked_raid`
   with a dialect-aware idempotent upsert: PostgreSQL `INSERT … ON CONFLICT (report_code) DO
   UPDATE`; for SQLite tests, catch `IntegrityError` and fall back to the update path. Closes
   the cross-socket duplicate window (FR-007).
3. **Boss name(s).** Persist the distinct encounter list onto the raid (see R4) and show a
   compact boss summary on the entry; render cleanly when none is known (FR-009).

**Rationale**: The "duplicate" the user sees is almost certainly *visual*: labels are
`"<guild> — <zone> — <date>"` with **date only**, so two reports from the same guild/zone/night
look identical. Showing the actual date **and time** (and boss) disambiguates them, and the
`ON CONFLICT` upsert closes the one real DB race. All of this reuses stored data — only the
boss list is new (R4).

**Alternatives rejected**:
- *Changing the dedup key off `report_code`* — rejected; `report_code` is the correct natural
  key and already unique. Merging distinct reports would hide real raids.
- *Storing a formatted date string* — rejected; keep the typed timestamp and format in the UI.

---

## R3 — PDF report fidelity (US3)

**Decision**: Extend the in-house `_markdown_flowables` converter in
`backend/app/services/pdf_report.py` rather than adding a dependency:
- **Tables**: detect a block whose lines contain `|` with a `---|---` separator row, and build
  a ReportLab `Table` with a header `TableStyle`; render each cell as a `Paragraph` so cell
  text wraps.
- **Numbered & mixed lists**: recognize `1.`/`2.` ordered lists and bullet lists that have an
  intro line (today the all-bullet guard drops them to one paragraph).
- **Long-token wrapping**: set `wordWrap="CJK"` on the body style (and table cells) so long
  unbroken tokens — report codes, URLs, ability names — break within the page margins
  (FR-013).
- **Context (optional)**: precede each answer with its originating user question as a small
  heading so the PDF reads as Q→A (improves readability; noted as an assumption in spec).
- Keep the existing graph pipeline and the `to_thread` offload unchanged.

**Rationale**: The actual defect is that GFM tables (which the agent is told to emit and the web
UI renders) fall through to the generic paragraph branch and print raw `| col | col |` — the
"renders badly" complaint. ReportLab has no HTML-table support in `Paragraph`, so tables must
become `Table` flowables regardless of approach; extending the existing ~35-line converter is
smaller and dependency-free versus swapping engines (YAGNI/DRY). The endpoint already returns
a valid file and 500s cleanly on failure (FR-015), so "not working anymore" is addressed by
fixing rendering + verifying end-to-end.

**Alternatives rejected**:
- *A markdown→PDF library (e.g. md2pdf) or HTML→PDF (WeasyPrint)* — heavier native deps, less
  layout control, and a much larger change than the defect warrants.

---

## R4 — Boss focus checkboxes (US4)

**Decision**: Capture-and-forward, mirroring the existing raid/graph capture backbone.
- New `backend/app/services/encounters.py::encounters_from_tool(...)` parses a successful
  `get_report_fights` result into a **distinct** boss list (deduped by `encounterID`, dropping
  trash/null encounters), each `{encounter_id, name, difficulty, kill}`.
- Persist that list onto `TrackedRaid.encounters` (feeds the sidebar boss display, R2) via the
  existing upsert path in `services/raids.py`.
- Emit a new typed `EncountersFrame` (`type:"encounters"`, `report_code`, `encounters:[…]`)
  from `ws.py::_handle_tool_end` right after the `tool_end`, so the UI can render checkboxes
  attached to that turn.
- Frontend: `EncounterPicker.tsx` renders a checkbox group under the agent message that
  surfaced the fights; selected boss names fold into the **next** user message text (visible,
  e.g. appended "`(Focus on: Boss A, Boss B)`"), so the user sees exactly what they asked and
  the agent receives a plain focused prompt. Selections reset per turn (FR-020).

**Rationale**: The fight list already exists in the `get_report_fights` result but never leaves
the backend (`_handle_tool_end` forwards only `{name, ok}`). Reusing the capture backbone +
one new frame is the minimal path. Folding bosses into the visible prompt (client-side) keeps
the interaction transparent and avoids a second server round-trip or a seq-0 special case.

**Alternatives rejected**:
- *Server-owned focus-prompt endpoint* (like `kickoff_prompt_for`) — unnecessary round-trip for
  what is just appending boss names to the user's text; the user benefits from seeing it.
- *A normalized `TrackedEncounter` table* — over-normalized for a short, read-mostly inline
  list (YAGNI); a JSON column matches the `captured_graphs.graph_json` precedent.

---

## R5 — Cached new-chat greeting (US5)

**Decision**: Generate once, cache per session, inject client-side.
- New `backend/app/greeting.py::get_greeting(app, model) -> str`: returns a cached greeting
  from `app.state.greeting_cache: dict[str, str]`, generating it on miss by running the real
  agent over a disposable session id (e.g. `"greeting-<model>"`) with the hidden kickoff
  `"Greetings, Barnaby!"` and collecting the streamed tokens — so the greeting carries the true
  Barnaby persona from the single-source `INSTRUCTION`.
- Prime the default model's greeting at **startup** in `main.py` lifespan via
  `asyncio.to_thread`/await (off the request path), so the first new chat is instant (FR-023).
- New `backend/app/api/greeting.py`: `GET /api/greeting?model=` → `GreetingResponse{greeting}`.
- Frontend: `newChat()` (in `App.tsx`) fetches `/api/greeting` and injects the text as a
  **display-only** agent message (no conversation row yet; the hidden kickoff is never shown —
  FR-022). The user's first real message then creates the conversation and proceeds normally
  through the existing WS path (FR-025). If the fetch fails or is slow and the user starts
  typing, the chat opens clean and late greetings are ignored (FR-024 + input-priority edge
  case).

**Rationale**: A cached canned string avoids a model call per new chat (snappy, matches the
"fail-closed, don't delay the user" ethos of `suggestions.py`). Reusing the agent runner for
generation keeps the persona DRY (no second hand-written greeting to drift). Display-only
injection avoids a seq-0 special case in persistence, which the codebase deliberately avoids
(`raids.py` comment).

**Alternatives rejected**:
- *Persisting the greeting as message seq 0* — reintroduces the seq-0 special case the project
  avoided; the greeting is session chrome, not durable analysis.
- *A hardcoded static greeting string* — loses the model's voice and would drift from the
  evolving Barnaby prompt (DRY violation).
- *Generating on first new chat (no startup prime)* — first chat would stall on a model call;
  startup priming makes it instant.

---

## R6 — Streaming transport: keep WebSocket (US6)

**Decision**: Keep the existing WebSocket frame protocol; do **not** migrate to the skill's
SSE-over-POST. Drive the spellcasting/streaming UI from the current frames, which already map to
the skill's event taxonomy:

| Skill event | Existing frame | Note |
|-------------|----------------|------|
| `run_start` | `meta` | carries conversation_id/seq at turn start |
| `tool_start`| `tool_start` | already carries `name` (+ `report_code`) |
| `tool_end`  | `tool_end` | **add** `summary` + `ms` (FR-032) |
| `tool_progress` *(optional)* | — | **new optional** `ToolProgressFrame` for determinate bars |
| `token`     | `token` | feeds `useSmoothText` |
| `done`      | `done` | completion flourish |
| `error`     | `error` | fizzle the run |

**Rationale**: The transport already works and the mapping is 1:1; an SSE rewrite of `ws.py`,
`agent_runner`, and the frontend socket client would be pure rework with no functional gain
(Simplicity-First). The only backend additions are the typed `tool_end.summary`/`ms` fields
(timed in `agent_runner.stream_response`, summarized by a new `services/tool_summary.py`) and an
optional `ToolProgressFrame`.

**Alternatives rejected**: SSE-over-POST per the skill — gratuitous given a working WS and the
constitution's Simplicity-First mandate.

## R7 — Frontend stack migration: full skill stack (US6)

**Decision** (user-directed full adoption): upgrade **React 18→19**; adopt **Tailwind v4** via
`@tailwindcss/vite` with a CSS-first `@theme` token block; add **shadcn/ui** (OKLCH tokens,
`cn()` util); **motion** (`motion/react`) for spell cards/bursts/stagger; **streamdown** to
replace `react-markdown` for streaming-safe markdown; **use-stick-to-bottom** for chat scroll;
**@tsparticles/react** + **@tsparticles/slim** for ambient particles; **react-icons/gi** for
game-icons.net glyphs.

**Rationale**: The skill's patterns are built around this stack; Streamdown (no broken markdown
mid-stream), motion (declarative spell-card lifecycle), and stick-to-bottom (AI-chat scroll) each
solve a real problem the current hand-rolled code does poorly. Tailwind v4 + shadcn provide the
token architecture the theme system needs.

**Sequencing / risk**: the migration is isolated as a **Foundational** step — upgrade React,
wire Tailwind, swap the renderer to Streamdown, and verify the app still builds and streams —
*before* any US6 visual work or US1–US5 frontend UI is layered on. This is the single highest-risk
item; it is done once, up front, and verified on its own.

**Alternatives rejected**: curated subset / CSS-only (offered, **declined** by the user);
staying on React 18 (fights current peer deps of motion/shadcn/streamdown).

## R8 — Single fixed theme; retire the background toggle (US6)

**Decision**: Ship **one** curated fantasy theme using the token architecture (color/font/glow/
texture as CSS variables on `:root`), with **no** user-facing theme or background switcher.
Remove the Phase-2 `BackgroundToggle` component and its `localStorage`/`config` background
registry. **Retain the existing background images** (`frontend/public/assets/*`) as the fixed
theme backdrop, layered with the skill's grain + vignette overlays for legibility.

**Rationale**: The user wants "one good theme we set" and confirmed the current background
pictures fit. A single theme is simpler than a switchable multi-theme engine (Simplicity-First)
while still using the token system so the look is coherent and easy to tune in one place (DRY).

**Alternatives rejected**: multi-theme switcher with View Transitions (the skill's §2.4) —
explicitly declined; coexisting theme + background toggle — rejected as two overlapping controls.

## R9 — Streaming render, spell cards & accessibility (US6)

**Decision**:
- **Smoothing**: a `useSmoothText(target, streaming)` hook releases buffered text on
  `requestAnimationFrame` at an adaptive rate (catch-up when behind) — the single biggest
  perceived-quality win (skill §3.1).
- **Renderer**: `StreamMarkdown.tsx` wraps **Streamdown** (append `rehypeWordSpans` to its
  default rehype plugins; memoizes completed blocks) and renders links with
  `target="_blank" rel="noopener noreferrer"` — this is also where **US1** source links get
  their new-tab behavior, so `Markdown.tsx` is retired in favor of it.
- **Ink-in**: per-word `.ink` spans animate via **CSS keyframes only** (not motion components)
  to stay at 60 fps for thousands of words.
- **Caret + flourish + growth**: ember caret on the streaming block, a one-shot gold sheen on
  `done`, and `layout` height easing on the message container.
- **Scroll**: `use-stick-to-bottom` with a "back to bottom" control.
- **Spell cards**: a `SPELLS` registry maps **every real tool name** (the 16 WCL tools +
  `web_search`) to an icon/hue/verb/flavor; unknown tools fall back to `DEFAULT_SPELL`. Cards go
  summoning → casting (RuneCircle + CastBar + rotating flavor) → resolved (burst → compact chip
  with `summary`+`ms`) / fizzled (shake + reason), min ~600 ms display, parallel cards stagger
  with `layout`.
- **Accessibility/perf**: `useReducedMotion()` / `prefers-reduced-motion` disables blur/rotation/
  particles (keep simple fades/static rune circles); particles capped 30–60 and paused on
  `document.hidden`; finished messages `React.memo`'d.

**Rationale**: Directly implements the skill's §3–§6 with its own performance guardrails; the
spell registry keeps per-tool presentation DRY and data-driven.

**Alternatives rejected**: JS/motion per-word animation (too many nodes for 60 fps); ad-hoc
per-tool UI (would duplicate presentation logic).

## Cross-cutting notes

- **Schema migration**: the one new column `tracked_raids.encounters` is added idempotently in
  the lifespan startup block (same pattern already used for `messages.status`), since the app
  uses `create_all` + targeted `ALTER … IF NOT EXISTS` rather than a migration tool.
- **Dependencies**: *Backend* adds none (ReportLab/matplotlib already present; greeting reuses the
  ADK runner). *Frontend* adds a substantial set for US6 (R7): React 19, Tailwind v4, shadcn/ui,
  motion, streamdown, use-stick-to-bottom, @tsparticles(+slim), react-icons/gi — justified in the
  plan's Complexity Tracking. `react-markdown` is replaced by `streamdown` (which also serves US1's
  link rendering).
- **GitNexus**: impact-analyze `_handle_tool_end`, `upsert_tracked_raid`, `stream_response`,
  `render_report_pdf`, and the agent `INSTRUCTION`/`build_agent` before editing (Principle VI).
