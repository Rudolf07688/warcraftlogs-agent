# Quickstart & Verification: feature 005

Setup, then per-story manual verification. Backend tests are automated; UI slices are verified here.

## Setup

```bash
uv sync
cd frontend && npm install && cd ..      # installs react-plotly.js, plotly.js-dist-min, katex, remark-math, rehype-katex
uv run pytest -q                         # backend suite (incl. new tests)
```

Env additions (`.env` / `.env.example`):
```
WCL_GUIDE_MODEL=gemini-3.6-flash         # web-search-capable model for background guides (US6)
WCL_CACHE_TTL_REPORT_S=86400             # optional (US4) immutable report-scoped TTL
WCL_CACHE_TTL_LEADERBOARD_S=3600         # optional (US4) volatile leaderboard TTL
```

Run:
```bash
uv run uvicorn backend.app.main:app --reload
cd frontend && npm run dev
```

## US1 — Profile & guild context
1. Open the Profile panel; add your **self** character (name/server/region), one **friend**, and set a
   **main guild**. Saves return immediately.
2. Ask "how are my parses?" with no name → the agent resolves to your self character.
3. Ask "how is our guild doing?" → answer is scoped to the saved guild.
4. Ask a population question ("best Mage spec overall this tier?") → answer is **not** narrowed to the
   guild. ✅ FR-004, FR-005, SC-001.
5. With the profile cleared, confirm all existing behavior is unchanged. ✅ FR-006.

## US2 — Interactive charts
1. Ask "plot the raid DPS over time for `<report>` fight `<n>`" → an interactive chart renders inline;
   hover shows values, drag zooms. ✅ FR-007, FR-010, SC-003.
2. Watch the stream: no broken/partial chart appears mid-stream (it pops in only when complete). ✅ FR-009.
3. Reload the app and reopen the conversation → the chart re-renders. ✅ FR-011, SC-003.
4. Ask something a chart can't support and confirm you still get the text answer + a clear note if no
   chart was produced. ✅ FR-012.

## US3 — Math/LaTeX
1. Ask the agent to "write the parse rotation as a formula" → inline and block math typeset cleanly
   (no raw `$$` / `\text{}`). ✅ FR-013, FR-014, SC-004.
2. Type a message mentioning a dollar amount ("it costs $5") → not rendered as math. ✅ FR-015.
3. Download the PDF of a reply containing math → math renders legibly (block equations as images). ✅ FR-016.

## US4 — Caching
1. Ask a question that triggers several WCL lookups; note `check_rate_limit` points.
2. Ask a follow-up reusing the same report/boss/filters → noticeably faster; rate-limit points for the
   reused lookups do **not** increase. ✅ FR-017, FR-018, SC-005.
3. (Automated) `uv run pytest -q backend/tests/test_wcl_cache.py` covers hits/misses/tiers/bypass/isolation.

## US5 — Per-message PDF
1. Produce a reply with a table, prose, a source link, and a chart.
2. Click the per-message "Download report" on that reply → the PDF contains that reply + its originating
   question + the chart, and **excludes** other messages. ✅ FR-022–FR-025, SC-006.
3. Confirm long tokens wrap and there's no raw markup/overflow. ✅ FR-025.

## US6 — Auto-fetched spec guide
1. Add/lock a self character → the save returns < ~1 s (`guide_status: "pending"`). ✅ FR-027, SC-007.
2. Within a short while, refresh the Profile panel → `guide_status: "ready"`.
3. Ask "how do I improve on this spec?" → the answer reflects the fetched guide. ✅ FR-029, SC-007.
4. Lock in a bogus/unresolvable name → it still saves; `guide_status: "failed"`; the agent still answers
   without a guide. ✅ FR-030.

## Regression
- Existing conversation-level PDF still works and now also includes any artifacts.
- Existing streaming, raid tracking, greeting, encounters, and spell cards unchanged.
- `uv run pytest -q` green; `cd frontend && npm run build` succeeds.
