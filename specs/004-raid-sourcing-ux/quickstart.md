# Quickstart: Raid Sourcing, Tracking & Report UX

Manual verification for the five Phase 3 slices. Assumes Phases 1–2 are running
(`uv run uvicorn backend.app.main:app` + `cd frontend && npm run dev`, or the built frontend),
a valid WCL API credential, and at least one real report code to query.

## Setup

```bash
uv sync
cd frontend && npm install && cd ..
uv run pytest -q                 # baseline green before edits
```

**US6 note**: the frontend stack is migrated to React 19 + Tailwind v4 + shadcn/ui + motion +
streamdown + use-stick-to-bottom + @tsparticles + react-icons/gi. After the Foundational
migration, verify the app still builds and streams before layering visual work:

```bash
cd frontend && npm install && npm run build && npm run dev
```

Run the backend and frontend, open the app in a browser.

## US1 — Warcraft Logs source links (P1)

1. Ask an analytical question about a specific report + fight (e.g. "Why did we wipe on the
   third pull in report `<code>`?").
2. **Expect**: the answer contains a clickable Warcraft Logs link; for a fight-specific claim it
   points to that fight (`#fight=<id>`), and for a player/metric claim it narrows further
   (`&source=&type=`).
3. Click a link → it opens `warcraftlogs.com` in a **new tab**; the chat is untouched.
4. Ask something answered from general knowledge (e.g. "what patch is current?") → **expect no
   fabricated WCL link**.

## US2 — Raid list: date/time, boss, no duplicates (P1)

1. Investigate a report, then in a **second** chat reference the **same** report again.
2. **Expect**: the sidebar shows **one** entry for that report (no duplicate).
3. **Expect**: the entry shows the raid's **own date and time** (not the last-asked time) and,
   when known, the **boss name(s)**.
4. (Race check, optional) From two browser tabs, fire a first-ever reference to the same new
   report nearly simultaneously → still **one** sidebar entry.

## US3 — PDF report renders correctly (P2)

1. Produce an analysis that includes a **markdown table**, **headings**, a **bulleted list**, a
   **numbered list**, a long token (a report code or URL), and at least one **graph**
   (ask for a DPS-over-time graph so `get_report_graph` runs).
2. Click **⬇ PDF** in the chat header.
3. **Expect** in the PDF: the table is an aligned table (not raw `| … |`); headings/lists are
   formatted; long tokens wrap inside the margins; the graph appears.
4. The file opens in a standard PDF viewer without errors.

## US4 — Boss focus checkboxes (P2)

1. Ask a question that lists a report's fights (e.g. "what pulls are in report `<code>`?").
2. **Expect**: a checkbox group of the distinct bosses appears under that answer (repeated pulls
   of one boss collapse to a single checkbox).
3. Select two bosses, type a question (e.g. "why were these low?"), send.
4. **Expect**: the sent prompt is scoped to those bosses (visible focus text) and the answer
   focuses on exactly them. Sending with **no** boss selected behaves as before.

## US5 — Warm Barnaby greeting on new chat (P3)

1. Click **+ New chat**.
2. **Expect**: a warm Barnaby greeting appears **without** typing anything; the hidden
   "Greetings, Barnaby!" kickoff is **not** shown.
3. Start several more new chats in the same session → **expect** the greeting appears promptly
   (served from cache, < ~1s).
4. Start a new chat and immediately start typing a real question → **expect** your input is not
   clobbered; the conversation proceeds normally with your question.

## US6 — High-fantasy UX polish (P1)

1. Load the app. **Expect**: one cohesive fantasy theme (fonts, glow, texture, retained
   background image with grain/vignette); **no** theme or background switcher control anywhere.
2. Ask a question that streams a long markdown answer with a table. **Expect**: text inks in
   smoothly (no burst jitter), the table never shows broken `|`/`**` mid-stream, an ember caret
   trails the output, and a gold completion sheen plays once when it finishes.
3. Ask something that triggers a tool call. **Expect**: a themed spell card (tool icon + rune
   circle + cast bar + rotating flavor), held briefly even if the tool is fast/cached, then
   resolving to a compact chip with a short summary + duration.
4. Trigger a failing tool (e.g. a bad report code). **Expect**: the card fizzles with a clear
   reason rather than vanishing.
5. Ask a comparison that fires several tools at once. **Expect**: multiple cards stack/stagger
   and each resolves independently.
6. Enable OS "reduce motion" and reload. **Expect**: blur/rotation/particles are gone, the UI is
   still fully usable, and streaming stays smooth.
7. Scroll up during streaming. **Expect**: auto-scroll stops fighting you and a "back to bottom"
   control appears.
8. Confirm a game-icons.net CC BY 3.0 attribution line is present and no Blizzard assets are used.

## Regression

```bash
uv run pytest -q                 # all backend tests green (incl. new US1–US5 tests)
```

- Confirm existing follow-up suggestions, web-grounding note, parallel tool calls, and the
  resizable sidebar (Phases 1–2) still work. **Note**: the Phase-2 background toggle is
  intentionally **removed** in US6 (single fixed theme) — verify it is gone, not broken.
- Run `gitnexus_detect_changes()` before committing to confirm only expected symbols/flows
  changed (per CLAUDE.md).
