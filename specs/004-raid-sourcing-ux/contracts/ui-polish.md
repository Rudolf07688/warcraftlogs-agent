# Contract: High-fantasy UX polish (US6)

Defines the UI-side contracts for the `react-modern-ui` full adoption: the frame→UI mapping, the
spell registry, the fixed theme tokens, and the accessibility/performance guarantees. Backend
transport is the existing WebSocket (see `websocket.md`).

## Stream → UI mapping

| Frame | UI reaction |
|-------|-------------|
| `meta` (turn start) | Show the "summoning" orb ("The archmage ponders…") |
| `tool_start` | Spawn a spell card for that tool; start the cast bar (indeterminate) |
| `tool_progress` *(optional)* | Switch that card's cast bar to determinate (`done/total`) |
| `tool_end` | Resolve (burst → compact chip with `summary` + `ms`) if `ok`, else fizzle (shake + reason) |
| `token` | Feed `useSmoothText`; first token shrinks the orb into the ember caret |
| `grounding` | Mark the turn as "used web search" (existing behavior, themed) |
| `suggestions` | Render follow-up buttons (existing behavior, themed) |
| `encounters` | Render the boss `EncounterPicker` under the turn (US4) |
| `done` | Completion flourish (gold sheen), fade the active-message border |
| `error` | Fizzle the whole run |

Rules:
- Cards display a **minimum ~600 ms** so fast/cached tools never flicker (FR-032).
- **Parallel** tool calls render as stacked, independently-resolving cards with `layout` + stagger (FR-033).
- Resolved chips persist in the message (collapsed, expandable) — the "spellbook" of what the agent did.

## Spell registry (`frontend/src/lib/spells.ts`)

```
Spell = { icon: IconType; hue: string; verb: string; flavor: string[] }
SPELLS: Record<toolName, Spell>
DEFAULT_SPELL: Spell   // fallback for any unmapped tool
```

- MUST map **every real tool name** the agent exposes: the 16 WCL tools
  (`get_selected_encounter`, `find_encounter`, `get_spec_options`, `get_rankings_distribution`,
  `compare_specs`, `get_report_fights`, `get_report_table`, `get_report_events`,
  `get_report_graph`, `get_report_rankings`, `get_report_player_details`,
  `get_report_master_data`, `get_character_zone_rankings`, `get_character_encounter_rankings`,
  `check_rate_limit`, `run_wcl_graphql`) plus `web_search`.
- Unknown/new tool names MUST fall back to `DEFAULT_SPELL` (never render blank/crash — FR-031).
- Icons come from `react-icons/gi` (game-icons.net). A **CC BY 3.0 attribution** line MUST appear
  in the app (e.g. footer/about). No Blizzard assets/logos/fonts (FR-035).

## Theme tokens (`frontend/src/index.css`)

- A single fixed theme: CSS variables on `:root` for `--background/--foreground/--card/--muted/
  --primary/--glow/--border/--font-display/--font-body`, consumed via Tailwind v4 `@theme inline`.
- **No** `data-theme` switcher, **no** background toggle (FR-027). The existing background
  image(s) in `frontend/public/assets/` are the fixed backdrop, layered with grain + vignette;
  chat text MUST stay legible over them (FR-028, SC-007).
- Display font for headings (e.g. Cinzel), readable body font for chat text — never a display
  font in long chat text.

## Streaming renderer (`frontend/src/components/StreamMarkdown.tsx`)

- Wraps **Streamdown** (streaming-safe markdown; memoizes completed blocks) with `remark-gfm`
  behavior and an appended `rehypeWordSpans` plugin for per-word `.ink` reveal (CSS keyframes only).
- Renders links with `target="_blank" rel="noopener noreferrer"` — this satisfies **US1/FR-003**
  (so `Markdown.tsx` is retired).
- Driven by `useSmoothText(target, streaming)` so text inks in at a steady adaptive rate (FR-029).
- Ember caret on the streaming block; one-shot completion flourish on `done`; `layout` height
  easing; **use-stick-to-bottom** for scroll with a "back to bottom" control (FR-030).

## Accessibility & performance (hard constraints)

- `prefers-reduced-motion` / `useReducedMotion()` disables ink blur, rotation, particles, and
  bursts; simple fades and static rune circles remain; UI stays fully usable (FR-034, SC-010).
- Per-word animation is **CSS only**; finished messages `React.memo`'d; particles capped 30–60 and
  paused on `document.hidden`; streaming sustains ~60 fps (FR-034, SC-010).

## Verification artifact

`quickstart.md` includes a US6 pass: cohesive single theme, smooth jitter-free streaming with no
broken markdown, spell cards through summoning→casting→resolved/fizzled (incl. a parallel-call
case and a cached fast call honoring the min display), a reduced-motion run, and a frame-rate
spot check.
