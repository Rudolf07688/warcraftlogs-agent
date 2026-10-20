# Implementation Plan: Proper PDF Generation

**Branch**: `017-proper-pdf-generation` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-proper-pdf-generation/spec.md`. Shortcut epic 99 (stories 108, 109, 110).

## Summary

The PDF renderer is rebuilt as **Markdown → sanitised HTML → print CSS → PDF**, replacing the hand-written Markdown-to-ReportLab converter.

- **Markdown**: findings Markdown from the unchanged feature 007 rewrite is parsed by **markdown-it-py**, with CommonMark plus GFM tables and strikethrough, task lists, and dollar maths that leaves currency alone.
- **Equations**: typeset on the server with matplotlib mathtext as SVG. Anything mathtext can't parse falls back to plain text through the existing `_unwrap_latex_text` helper.
- **Sanitising**: the HTML is cleaned with **nh3**, and remote images become their alt text.
- **PDF**: **WeasyPrint** renders it with one print stylesheet. That covers the title block, running header, "Page X of Y", headings kept with their content, repeating table headers, wrapping, and a clean neutral style with tavern-brown accents.
- **Fetch lockdown**: WeasyPrint may only fetch `data:` URLs, so nothing remote or local (`file:`) can be pulled in.
- **Charts**: they stay on matplotlib but output **SVG** with one shared print style (line style and marker per series for black-and-white printing). They go in a Charts section after the findings, with numbered HTML captions and source links.

Endpoints, file names, the findings rewrite, scope filtering, fail-closed errors and the frontend are unchanged. ReportLab and the unused `markdown` package are removed.

## Technical Context

**Language/Version**: Python 3.14 (backend only). No frontend change.

**Primary Dependencies**:
- FastAPI and asyncio (unchanged);
- **new**: `weasyprint` (70), `markdown-it-py` (4.2), `mdit-py-plugins` (0.6), `nh3` (0.3);
- **kept**: matplotlib (mathtext and charts);
- **removed**: `reportlab`, and `markdown` (never imported);
- **test-only**: `pypdf`.

**System packages (container)**: `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`, `fonts-noto-cjk`, `fonts-noto-color-emoji`. The existing `fonts-dejavu-core`, `libfreetype6` and `libpng16-16` stay.

**Storage**: N/A. Reports are generated on demand. No database or Redis change.

**Testing**: pytest (`uv run --extra test pytest`). A fixture corpus of 20 or more findings documents is checked with pypdf text and link extraction. There are also unit tests for the HTML stage and the chart helpers, and the existing endpoint tests stay. No network.

**Target Platform**: Linux containers (`python:3.14-slim`, Debian trixie) and local `uv run` on the Ubuntu dev host.

**Project Type**: Web service (FastAPI backend + React frontend). This is a backend-only change.

**Performance Goals**:
- Render step 0.5 s or less for a typical report; the spike measured 0.35 s against today's 1.81 s.
- End-to-end download stays within today's time and under 30 s (SC-005), which is dominated by the unchanged findings LLM call.

**Constraints**:
- Rendering stays off the event loop (`asyncio.to_thread`, FR-022).
- No network or filesystem fetches during rendering (FR-006).
- Any failure gives a 500 and no file (FR-020).
- PDFs stay well under 5 MB; the spike produced 42 KB.

**Scale/Scope**:
- About 6 source files touched (`pdf_report.py` rewritten, `charts.py`, `api/reports.py`, `wcl_agent/benchmark.py`, `pyproject.toml`/`uv.lock`, `backend/Dockerfile`), plus docs (`README.md`, `documentation/ai_guide.md`).
- About 25 new or rewritten tests and 20 or more fixture documents.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse | ✅ | Reuses `_unwrap_latex_text` (maths fallback), `ChartSpec`, `_bounded` and the Plotly path, `report_synthesis`, the scope filtering and the fail-closed handling in `api/reports.py`. The two copies of the matplotlib plotting boilerplate (`charts.chart_spec_to_matplotlib` and `pdf_report._graph_image`) merge into one print style in `charts.py`. The WCL fight URL format gets one public builder (`report_link`) instead of a third copy. The unused `markdown` dependency is removed. |
| II. Step-wise delivery | ✅ | Slices, each testable on its own: (1) dependencies, Dockerfile and `findings_to_html` with its unit tests (US1, no PDF yet); (2) the WeasyPrint shell, CSS, title block and fetch lockdown, with the corpus test (US1 and US2 MVP); (3) SVG charts and the Charts section (US3); (4) the `ReportDocument` wiring in `api/reports.py`, plus the partial flag and the timing log line; (5) docs, ReportLab removal, then the live and black-and-white checks. |
| III. Simplicity | ✅ | Plain functions in one module. No template engine: the HTML shell is about 30 lines of escaped f-string. No report caching, no style option (clarify Q2), and no page-size setting. A browser renderer was rejected (research R1). New dependencies are justified under Complexity Tracking. |
| IV. Typed contracts | ✅ | The `ReportDocument` and `ReportFigure` dataclasses replace the `messages`/`graphs`/`artifacts` dict lists at the API-to-renderer boundary. HTTP responses are unchanged (binary PDF and the existing error `detail` strings). |
| V. Async backend | ✅ | Rendering stays synchronous inside `asyncio.to_thread`. Endpoints are unchanged. |
| VI. GitNexus | ✅ | Upstream `impact` was run. `chart_spec_to_matplotlib` is **LOW**: its only callers are `_artifact_image` and `render_report_pdf`. `_render` is **LOW**: `_synthesize_and_render`, `download_report` and `download_message_report`. `render_report_pdf` came back **UNKNOWN** (no resolved callers, because it is passed as a callable to `asyncio.to_thread`). A text search confirms its callers are `api/reports.py::_render`, `backend/tests/test_reports.py` and `backend/tests/test_pdf_report.py`. Re-run `impact` before each symbol edit, and `detect-changes --scope all` before committing. |
| VII. shadcn UI | N/A | No frontend change. |
| VIII. Backlog sync | ✅ | Stories 108, 109 and 110 are already In Progress in the Q4 iteration. They move to Under Review when the implementation is done, and `/shortcut-sync` runs at commit time. |

**Result**: PASS. The three new runtime dependencies and the larger image are justified below.

**Post-design re-check (after Phase 1)**: PASS. The design adds no layers beyond the module-level functions in the contract. The partial-answer flag and the timing log line are the only behaviour beyond the renderer swap, and both are needed by spec items (an edge case and SC-005).

## Project Structure

### Documentation (this feature)

```text
specs/017-proper-pdf-generation/
├── plan.md              # This file
├── research.md          # Phase 0: R1–R11 decisions + spike results
├── data-model.md        # Phase 1: ReportDocument / ReportFigure
├── quickstart.md        # Phase 1: tests, live check, B/W print, image check
├── contracts/
│   ├── report-endpoints.md   # HTTP endpoints (unchanged) + what changes behind them
│   └── report-renderer.md    # render pipeline, sanitiser allow-list, fetch policy, CSS rules, chart helpers
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
backend/
├── Dockerfile                         # + pango/harfbuzz libs, Noto CJK + Color Emoji fonts
├── app/
│   ├── api/reports.py                 # build ReportDocument (scope, question, partial, figures); timing log
│   └── services/
│       ├── pdf_report.py              # REWRITTEN: ReportDocument/ReportFigure, findings_to_html,
│       │                              #   maths render rules, nh3 sanitise, HTML shell, REPORT_CSS,
│       │                              #   render_report_pdf (WeasyPrint, data:-only fetcher)
│       └── charts.py                  # chart_spec_to_svg (was _to_matplotlib), graph_to_svg (moved),
│                                      #   shared print style + figure_to_svg; plotly path unchanged
└── tests/
    ├── fixtures/findings/*.md         # NEW: ≥20 findings docs (real exports + per-element edge cases)
    ├── test_pdf_report.py             # REWRITTEN: corpus, findings_to_html units, fetch lockdown
    ├── test_charts.py                 # updated for SVG output + B/W style
    ├── test_reports.py                # render calls → ReportDocument; endpoint asserts unchanged
    └── test_message_report.py         # + partial-answer note

wcl_agent/benchmark.py                 # _fight_link → public report_link(code, fight_id=None)
pyproject.toml / uv.lock               # + weasyprint, markdown-it-py, mdit-py-plugins, nh3; − reportlab, − markdown; test: + pypdf
README.md, documentation/ai_guide.md   # PDF export sections: new renderer, no reportlab
```

**Structure Decision**: The existing web-application layout is kept. All renderer logic stays in `backend/app/services/pdf_report.py` (one module, Principle III), and all chart drawing in `backend/app/services/charts.py`. There are no new packages or directories except the test fixture folder.

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `weasyprint` + Pango/HarfBuzz system libraries | A real paged-media engine gives running headers, "page X of Y", headings kept with content and repeating table headers (FR-009 to FR-011) from CSS alone. | Patching the ReportLab parser has failed three times, and every new construct needs new parser code. Headless Chromium adds about 300 MB and a browser subprocess (R1). |
| `markdown-it-py` + `mdit-py-plugins` | A spec-compliant parser with tables, task lists and currency-safe maths (FR-002, FR-005). | The regex parser is the root cause of the bug. Python-Markdown (installed but unused) handles nested lists and maths poorly, so it is removed instead (R2). |
| `nh3` | Model output can contain raw HTML, which must be honoured or dropped and never shown or executed (FR-006). | `html=False` shows tags as text (FR-001). bleach is deprecated (R3). |
| `fonts-noto-cjk` + `fonts-noto-color-emoji` (about +100 MB image) | Korean, Chinese and Taiwanese realm and character names, and emoji, must not show as boxes (FR-007 and the emoji edge case). | DejaVu alone covers only Latin, Greek and Cyrillic. Bundling fonts in the repo means licence and asset files. If image size ever matters more than CJK names, drop `fonts-noto-cjk` (a one-line change, R7). |
