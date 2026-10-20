---

description: "Task list for feature 017 — Proper PDF Generation"
---

# Tasks: Proper PDF Generation

**Input**: Design documents from `specs/017-proper-pdf-generation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (report-endpoints.md, report-renderer.md), quickstart.md

**Tests**: Included. The plan (research R11) and quickstart.md specify a fixture corpus, unit tests and an endpoint regression, and SC-001 to SC-003 can only be checked that way.

**Organization**: Tasks are grouped by user story, so each story can be built and tested on its own.

**Constitution reminders**:
- Run `node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .` before editing any existing function (Principle VI).
- `render_report_pdf` comes back as UNKNOWN in GitNexus. Its callers are `api/reports.py::_render`, `test_reports.py` and `test_pdf_report.py`.
- Commands run from the repo root. Tests run with `uv run --extra test pytest -q`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: The user story the task belongs to (US1, US2, US3)

## Path Conventions

Web app: backend code is in `backend/app/`, tests in `backend/tests/`, and the shared agent package in `wcl_agent/`. There is no frontend change.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the new libraries and system packages. Nothing behaves differently yet.

- [X] T001 Add runtime dependencies with `uv add weasyprint markdown-it-py mdit-py-plugins nh3` and the test-only dependency with `uv add --optional test pypdf`. This updates `pyproject.toml` and `uv.lock`. Do **not** remove `reportlab` or `markdown` yet; that happens in T033.
- [X] T002 [P] In `backend/Dockerfile`, extend the existing `apt-get install` line with `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-noto-cjk fonts-noto-color-emoji`, keeping `libfreetype6 libpng16-16 fonts-dejavu-core`. Change the comment to say WeasyPrint and matplotlib (not ReportLab). See research R7 and R8.
- [X] T003 [P] Check the local toolchain: `uv run python -c "import weasyprint, markdown_it, mdit_py_plugins, nh3; print(weasyprint.__version__)"` must print `70.x`. If Pango is missing on the host, follow quickstart.md §0.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Get the new pipeline working end to end: typed input, then SVG chart helpers, then the WeasyPrint render with fetches locked down, then the API wiring. After this phase every report is produced by WeasyPrint. The styling and Markdown fidelity come in the story phases.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] In `wcl_agent/benchmark.py`, promote `_fight_link(code, fight_id)` to a public `report_link(code: str, fight_id: int | None = None) -> str`. It returns `https://www.warcraftlogs.com/reports/{code}`, with `#fight={fight_id}` appended when `fight_id` is set. Update the existing callers in the same file. Run `impact` on `_fight_link` first.
- [X] T005 [P] In `backend/app/services/charts.py`, add `figure_to_svg(fig) -> bytes` (SVG, `bbox_inches="tight"`, always `plt.close(fig)`) and `chart_spec_to_svg(spec: ChartSpec) -> bytes`. The latter is ported from `chart_spec_to_matplotlib` with the same drawing per `kind`, but **no** `ax.set_title` and SVG output in place of a ReportLab `Image`. Move `_series_from_graph` from `pdf_report.py` into this module and add `graph_to_svg(graph_json: dict) -> bytes | None` (`None` when there is no plottable series). Delete `chart_spec_to_matplotlib` and the `reportlab` imports from this module. Run `impact` on `chart_spec_to_matplotlib` first. Its only callers are `pdf_report._artifact_image` and the tests.
- [X] T006 In `backend/app/services/pdf_report.py`, add the frozen dataclasses `ReportFigure(title: str, svg: bytes | None, source_url: str = "")` and `ReportDocument(title, scope: Literal["conversation","message"], generated_at: datetime, body_markdown: str, question: str | None = None, partial: bool = False, figures: tuple[ReportFigure, ...] = ())`, exactly as in data-model.md.
- [X] T007 Rewrite `render_report_pdf` in `backend/app/services/pdf_report.py` to the new signature `render_report_pdf(doc: ReportDocument) -> bytes`. It should:
  - build a minimal HTML shell (`<h1>` title, the body from a first `findings_to_html` that just runs markdown-it `commonmark` plus `table`, and a Charts section with `<figure><img src="data:image/svg+xml;base64,…"></figure>` for each figure that has SVG);
  - render with `weasyprint.HTML(string=…, base_url=None, url_fetcher=URLFetcher(allowed_protocols={"data"})).write_pdf(stylesheets=[CSS(string=REPORT_CSS)])`, with `REPORT_CSS` a placeholder for now;
  - HTML-escape every interpolated value except the `findings_to_html` output.

  Delete the ReportLab code: `_inline_md_to_rl`, `_mathtext_image`, `_ensure_pdf_styles`, the table helpers, `_markdown_flowables`, `_graph_image`, `_artifact_image` and the ReportLab and `plt` imports. **Keep** `_unwrap_latex_text` and the `_INLINE_*`/`_BLOCK_MATH_RE` notes for T018. Update the module docstring (pure, synchronous, no DB, no network).
- [X] T008 In `backend/app/api/reports.py`, change `_render` and `_synthesize_and_render` to build a `ReportDocument`:
  - `scope`;
  - `question`, for the message scope only;
  - `partial=(msg.status == "partial")` from `download_message_report`;
  - `figures`: captured graphs first, via `charts.graph_to_svg(g.graph_json)` with title `f"{data_type} — {report_code}"` and `source_url=report_link(report_code, fight_id)`; then artifacts, via `ChartSpec.model_validate` and `charts.chart_spec_to_svg`, with title `spec.title` and `source_url=spec.source_url`;
  - any validation or drawing exception for one figure gives `svg=None`. It must not fail the report.

  Pass `body_markdown=findings_md` directly; the synthetic `messages` list goes away. Keep the `asyncio.to_thread`, the fail-closed `HTTPException(500, "pdf_generation_failed")`, the titles, the file names and the scope filtering exactly as they are (contracts/report-endpoints.md). Replace `_graph_dicts`/`_artifact_dicts` with a single `_figures(graphs, artifacts) -> tuple[ReportFigure, ...]`.
- [X] T009 Update the existing tests to the new signatures so the suite is green again:
  - `backend/tests/test_reports.py`: the direct `render_report_pdf(...)` calls take a `ReportDocument`. The endpoint assertions don't change.
  - `backend/tests/test_charts.py`: `chart_spec_to_matplotlib` → `chart_spec_to_svg`. Assert the result starts with `b"<?xml"` or contains `b"<svg"`.
  - `backend/tests/test_pdf_report.py`: delete the tests that import ReportLab internals (`_markdown_flowables`, `_inline_md_to_rl`, `reportlab.platypus.Image`). Port the remaining `%PDF` smoke tests to `ReportDocument`.
  - Then run `uv run --extra test pytest -q`. The full suite must pass.

**Checkpoint**: Both download endpoints return WeasyPrint PDFs with charts, the fail-closed paths still work, and the user story phases can begin.

---

## Phase 3: User Story 1 - Clean, readable report text (Priority: P1) 🎯 MVP

**Goal**: Every Markdown element in FR-002 renders as real formatting. No syntax or markup is visible, links can be clicked, maths is typeset or falls back to plain text, currency is left alone, and raw HTML is sanitised. Nothing is ever fetched.

**Independent Test**: Run the fixture corpus test. Every document renders, its extracted text has no markers, and its links are URI annotations (SC-001 to SC-003). Then download a real report and look at it (quickstart §2.3).

### Tests for User Story 1 ⚠️ (write first, must fail)

- [X] T010 [P] [US1] Create the hand-written edge-case corpus in `backend/tests/fixtures/findings/`, one `.md` per item:
  - `headings.md` (levels 1–4);
  - `emphasis.md` (bold, italic, bold-italic, strikethrough, inline code);
  - `nested-lists.md` (three levels, bullets mixed with numbers, authored numbering starting at 3);
  - `task-list.md`;
  - `blockquote-hr.md`;
  - `table-formatting.md` (alignment, bold and links in cells, ragged rows);
  - `wide-table.md` (8 columns, long cells);
  - `links.md` (WCL report, fight and character links);
  - `math.md` (inline `$a^2$`, `$$\text{A} \longrightarrow \text{B}$$`, `\[…\]`, a bad `$$\badcommand{x}$$`);
  - `currency.md` ("costs $5 and $10");
  - `raw-html.md` (`<br>`, `<b>`, `<script>alert(1)</script>`, `<!-- c -->`, `<iframe>`);
  - `remote-image.md` (`![boss](https://evil.example/x.png)` and an image with no alt text);
  - `long-token.md` (a 150-character unbroken token and a URL);
  - `code-block.md` (a long line);
  - `names.md` (Ælfwyn, Kâzzak, Иванушка, 김철수, 王小明, an emoji 🔥);
  - `no-findings.md` (the exact "No substantive findings" document from `report_synthesis._SYSTEM`).
- [X] T011 [P] [US1] *(Done 2026-10-19 with 7 real agent answers, `real-01…07.md`, the longest answer from each of 7 recent local conversations. They are raw model Markdown and messier than findings. The synthesis step couldn't run because the Vertex ADC token had expired. To add synthesized findings later: `gcloud auth application-default login`, then re-run the export.)* Add at least 6 **real** findings documents to `backend/tests/fixtures/findings/real-*.md`. Export recent agent conversations from the local Postgres, run them through `report_synthesis.synthesize_findings` once (needs Vertex credentials), and save the Markdown it returns. Strip nothing. These are the owner's own characters. The corpus has to reach **20 or more** files in total (SC-001).
- [X] T012 [P] [US1] In `backend/tests/test_pdf_report.py`, add unit tests for `findings_to_html(markdown)`:
  - nested `<ul>`/`<ol>` three deep, with `<ol start="3">` kept;
  - task-list `<input type="checkbox" checked disabled>`;
  - `th`/`td` `text-align` kept;
  - "$5 and $10" stays as text with no `<img>`;
  - `$a^2$` becomes an `img.math-inline` with a `data:image/svg+xml` source;
  - `$$\badcommand{x}$$` becomes `<em>` text with no `\`, `{` or `$`;
  - `<script>` is removed together with its content, while `<br>` and `<b>` stay;
  - an `<img>` with a remote `src` turns into its alt text, or into the URL when there is no alt text;
  - no `href` with a `javascript:` scheme survives.
- [X] T013 [P] [US1] In `backend/tests/test_pdf_report.py`, add a parametrised **corpus test** over every file in `fixtures/findings/`. Render a `ReportDocument` with the file as `body_markdown`, check that the PDF starts with `%PDF`, and use `pypdf` to extract the text from every page. Assert that none of `**`, `__`, `##`, `|---`, `$$`, `](`, `<br`, `<b>`, `<script`, `&lt;`, `&gt;` or `\text` appears (skip backticks and `<` inside `code-block.md`, where they are literal). Assert that every `[text](url)` in the source appears as a `/URI` link annotation (SC-003). For `names.md`, assert that every name appears in the extracted text.
- [X] T014 [P] [US1] In `backend/tests/test_pdf_report.py`, add a **fetch lockdown** test. A document containing `<img src="file:///etc/hostname">`, `<img src="http://127.0.0.1:9/x.png">` and an inline `<span style="background:url(http://127.0.0.1:9/y)">` must render successfully. Monkeypatch `socket.socket.connect` and `builtins.open` (for paths outside the venv and fonts) to raise if they are called. Assert they were never called, and that the hostname's contents do not appear in the extracted text.

### Implementation for User Story 1

- [X] T015 [US1] In `backend/app/services/pdf_report.py`, implement the full `findings_to_html` parser setup. Use `MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])` with `tasklists_plugin` and `dollarmath_plugin(allow_space=False, allow_digits=False, double_inline=True)`. Build the parser once at module level.
- [X] T016 [US1] In `backend/app/services/pdf_report.py`, add the `math_inline` and `math_block` render rules. Render with matplotlib mathtext to SVG through `charts.figure_to_svg` (the figure is sized to the text, inline at body size, block at about 1.25× and centred) and emit `<img class="math-inline|math-block" src="data:image/svg+xml;base64,…">`. If mathtext raises, fall back to `<em>{html.escape(_unwrap_latex_text(src))}</em>` (FR-004). Remove the `_INLINE_*`/`_BLOCK_MATH_RE` regexes, which dollarmath replaces.
- [X] T017 [US1] In `backend/app/services/pdf_report.py`, add sanitising after rendering. Call `nh3.clean` with the tag and attribute allow-list from contracts/report-renderer.md, `url_schemes={"http","https","mailto","data"}`, `link_rel=None`, `clean_content_tags={"script","style","iframe","object","embed"}`, and a `style` attribute filter that keeps only `text-align`. Then a small pass replaces any `<img>` whose `src` isn't `data:` with its escaped `alt`, or with the URL as text when there is no `alt` (the remote-image edge case).
- [X] T018 [US1] Add the content-element rules to `REPORT_CSS` in `backend/app/services/pdf_report.py`:
  - nested-list indentation and markers;
  - `.task-list-item { list-style: none }` with the checkbox inline (the spike gap);
  - `code`/`pre` (`white-space: pre-wrap`, DejaVu Sans Mono, light grey block);
  - `blockquote` (left rule);
  - `hr`;
  - `img.math-inline { vertical-align: middle; height: 1.1em }`, `img.math-block { display: block; margin: 6pt auto }`;
  - a base `table` style with `width: 100%`.
- [X] T019 [US1] Run `uv run --extra test pytest -q backend/tests/test_pdf_report.py` and make T012–T014 pass. Rasterise two corpus PDFs with `pdftoppm -r 70 -png` and look at them: no markers, task lists inline, maths aligned.

**Checkpoint**: US1 is the MVP. Report text is clean and safe, even before the layout polish.

---

## Phase 4: User Story 2 - A report that looks like a real document (Priority: P2)

**Goal**: The title block (scope, UTC time, question), the partial-answer note, the running header, "Page X of Y", headings kept with their content, table header rows repeated after page breaks, no overflow on A4 or Letter, and one clean neutral style with tavern-brown accents.

**Independent Test**: Render `wide-table.md` combined with a long multi-page fixture. Check the title block text, the "Page 1 of N" and running header text through pypdf, and that the table header appears again after the break. Then look at the result on screen and printed in greyscale (quickstart §2.3, §2.5).

### Tests for User Story 2 ⚠️

- [X] T020 [P] [US2] In `backend/tests/test_pdf_report.py`, add **document-structure** tests:
  - the conversation scope's page-1 text contains the title, "Whole conversation" and `UTC`;
  - the message scope's page-1 text contains "Single answer" and the question text;
  - `partial=True` gives text containing "partial answer";
  - a long document (repeat `wide-table.md` until it spans 3 pages or more) has "Page 1 of N" on page 1 with N ≥ 3;
  - page 2's text contains the running title, and page 1 doesn't repeat it as a header;
  - the table's header-row text appears on at least 2 pages (repeated `thead`);
  - a title containing `<b>&` is escaped (it appears literally and isn't parsed as markup).
- [X] T021 [P] [US2] In `backend/tests/test_message_report.py`, add a test that seeds an agent message with `status="partial"`, downloads its per-message report, and asserts that the extracted PDF text contains "partial answer". Add a second check that the question text appears in the title block. Mock the synthesis as the existing tests do.

### Implementation for User Story 2

- [X] T022 [US2] In `backend/app/services/pdf_report.py`, build the title block and the partial note as in contracts/report-renderer.md:
  - `<header class="title-block">` holding the `<h1 class="report-title">` title, a `.meta` line ("Whole conversation" or "Single answer", then `· Generated {YYYY-MM-DD HH:MM} UTC`), and, for the message scope, `<blockquote class="question">`;
  - then `<p class="partial-note">Interrupted — partial answer</p>` when `doc.partial`;
  - all of it escaped.
- [X] T023 [US2] Add the page and style rules to `REPORT_CSS` in `backend/app/services/pdf_report.py`:
  - `@page { size: A4; margin: 20mm 18mm }`;
  - `.report-title { string-set: title content() }`;
  - `@page { @top-center { content: string(title) } @bottom-right { content: "Page " counter(page) " of " counter(pages) } }`, with `@page :first { @top-center { content: none } }`, and the font stack and 8pt grey text set inside the margin boxes (the spike gap);
  - `h1–h4 { break-after: avoid }`;
  - `tr, figure, pre, blockquote { break-inside: avoid }`;
  - `thead { display: table-header-group }`;
  - `body`, `td` and `th` with `overflow-wrap: anywhere`;
  - body font stack `"DejaVu Sans", "Noto Sans CJK SC", "Noto Color Emoji", sans-serif` at 10pt/1.45;
  - a white page with near-black text;
  - accents `#4b2e1e` on the title, headings, table header row and title-block rule;
  - table banding `#f3ece0`; borders `#b8a07e`;
  - `.partial-note` and `.question` styles.
  
  No parchment tint and no decorative fonts (FR-013, FR-014).
- [X] T024 [US2] Run the US2 tests. Then render the long fixture a second time with an extra `CSS(string="@page { size: letter }")` stylesheet and rasterise both. Check that nothing runs past the margins on A4 or Letter and that no heading sits alone at the bottom of a page (FR-010, FR-011).

**Checkpoint**: US1 and US2 both work. The report reads like a shareable document.

---

## Phase 5: User Story 3 - Charts that belong in the report (Priority: P3)

**Goal**: A Charts section on a new page after the findings. Each chart is numbered and captioned in HTML ("Figure N — title", plus a clickable source link), sharp vector SVG with a print style that survives black and white. A chart that can't be drawn shows "Chart unavailable", and the section is left out when there are no charts.

**Independent Test**: Download a report from a conversation with one captured graph and one analyst chart. Check the captions, the order, the source link, the sharpness at 200% zoom and a greyscale print (quickstart §2.3, §2.5).

### Tests for User Story 3 ⚠️

- [X] T025 [P] [US3] In `backend/tests/test_charts.py`, assert the following:
  - `chart_spec_to_svg` returns SVG for every value in `CHART_KINDS`;
  - a 3-series line chart's SVG contains at least 2 distinct `stroke-dasharray` patterns, or distinct marker paths (FR-017);
  - a 1-series chart has no legend, and a 2-series chart has one (check for the legend labels in the SVG text);
  - the spec title isn't drawn in the SVG;
  - `graph_to_svg` returns `None` for `{}` and for a series with no points, and returns SVG for the `_GRAPH` payload from `test_pdf_report.py`.
- [X] T026 [P] [US3] In `backend/tests/test_pdf_report.py`, add **Charts section** tests:
  - two figures give the text "Figure 1 — " and "Figure 2 — " in order, after the findings, on a later page than the findings start;
  - a figure with `source_url` gives a `/URI` annotation to that URL;
  - a figure with `svg=None` gives "Chart unavailable", and the PDF is still valid;
  - no figures means no "Charts" heading in the text.
  
  Extend `backend/tests/test_message_report.py::test_message_report_is_scoped_and_valid` to assert that the first answer's PDF contains "Figure 1" and the second answer's PDF doesn't (FR-021).

### Implementation for User Story 3

- [X] T027 [US3] In `backend/app/services/charts.py`, add one shared print style, used by both `chart_spec_to_svg` and `graph_to_svg`:
  - figure size about 6.5×3.2 in;
  - a cycle of (line style, marker) per series, for example `("-", "o"), ("--", "s"), (":", "^"), ("-.", "D")`, with `markevery` so long series aren't cluttered (FR-017);
  - a colour cycle that starts with tavern brown and stays distinguishable in greyscale;
  - a light grid; axis labels when set;
  - a legend only when there is more than one series;
  - axes, ticks and labels in DejaVu Sans;
  - for bar charts, hatch patterns per series in place of line styles.
  
  `chart_spec_to_plotly` stays unchanged.
- [X] T028 [US3] In `backend/app/services/pdf_report.py`, finish the Charts section:
  - `<section class="charts">` with `<h2>Charts</h2>`, only when `doc.figures` isn't empty;
  - one `<figure>` per figure, numbered by position, holding either the SVG `<img>` or `<p class="chart-unavailable">Chart unavailable</p>`, and `<figcaption>Figure {n} — {escaped title}</figcaption>`, plus ` · <a href="{source_url}">source</a>` when `source_url` is set;
  - CSS: `.charts { break-before: page }`, `figure img { width: 100% }`, a caption style, and a muted, italic unavailable note.
- [X] T029 [US3] Run `uv run --extra test pytest -q backend/tests/test_charts.py backend/tests/test_pdf_report.py backend/tests/test_message_report.py`. Rasterise a report with charts, and also convert it to greyscale (`pdftoppm -gray`), to check that the series stay distinguishable (SC-007).

**Checkpoint**: All three user stories work on their own and together.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Remove dead dependencies, add observability, update docs, run the checks and sync the board.

- [X] T030 In `backend/app/api/reports.py`, log one INFO line after a successful render: `pdf rendered scope=%s pages=%d figures=%d ms=%d`. Time the `asyncio.to_thread` call with `time.perf_counter()`. Count pages with a cheap `pdf_bytes.count(b"/Type /Page")` and leave out `/Pages` matches, or return the page count from the renderer if that is simpler. Don't add a pypdf runtime dependency (research R10, SC-005).
- [X] T031 [P] Update `README.md`: the PDF export bullets (~line 154) now say "rendered with WeasyPrint from sanitised HTML; matplotlib SVG charts". Mention the system packages for local runs and point to quickstart §0.
- [X] T032 [P] Update `documentation/ai_guide.md`: the PDF export, chart and maths notes (~lines 327–360 and ~434) should describe the pipeline (markdown-it → mathtext SVG → nh3 → WeasyPrint with the `data:`-only fetcher), `ReportDocument`, `chart_spec_to_svg`/`graph_to_svg`, and that the PDF typesets maths and no longer uses italic stand-ins. Remove the ReportLab mentions.
- [X] T033 Remove the now-unused dependencies with `uv remove reportlab markdown`, which updates `pyproject.toml` and `uv.lock`. Running `grep -rn --include='*.py' -E "reportlab|^\s*import markdown\b" backend wcl_agent` must find nothing.
- [X] T034 Run the full suite, `uv run --extra test pytest -q`, plus the project linter and formatter on the changed files. Then run `node .gitnexus/run.cjs detect-changes --scope all --repo .` and check that the affected symbols are only the ones the plan names (`render_report_pdf`, `chart_spec_*`, `_render`/`_synthesize_and_render`/the download handlers, `report_link`). Re-run if the result is `partial` or `truncated`.
- [X] T035 *(Done 2026-10-19: the image builds, WeasyPrint 70.0 imports, and DejaVu Sans, Noto Sans CJK SC and Noto Color Emoji are present. All 23 fixtures plus a chart render in 3.3 s inside the container. The image grew from 770 MB to **984 MB (+214 MB)**, above the ~120 MB estimate in R7; `fonts-noto-cjk` is the bulk of it.)* Build the image and check it (quickstart.md §3): `docker compose build backend`; `weasyprint.__version__` prints in the container; `fc-list` shows DejaVu Sans, Noto Sans CJK and Noto Color Emoji; record the image size change (expected about +120 MB).
- [ ] T036 Live check (quickstart.md §2), **owner-assisted**: download a conversation report and a single-answer report from real raid chats, then do the greyscale print and the old-vs-new comparison against `main` (SC-004, SC-006, SC-007). Confirm the `pdf rendered … ms=` log line shows a render time of 0.5 s or less (SC-005).
- [X] T037 *(Done 2026-10-20 at commit time: stories 108, 109 and 110 confirmed Under Review; the sync also ticketed the new todo bullets as sc-163…168 and epic 162.)* Run `/shortcut-sync`. Move stories 108, 109 and 110 to **Under Review**, never Done (constitution Principle VIII). The `todo.md` line "PDF reports still look terrible…" is left for the owner to strike through once the stories are Done.

---

## Phase 7: QA follow-ups (sweep 2026-10-19, `qa-reports/2026-10-19/README.md`)

**Purpose**: Fix the top five findings before committing. Plan: `~/.claude/plans/virtual-forging-wind.md`.

- [X] T038 Only renderer-made images reach WeasyPrint (SEC-001/002): in `backend/app/services/pdf_report.py`, put maths placeholders in the markup and swap the images in after nh3; `_images_to_text` turns every model `<img>` (including `data:`) into text; drop `data` from the URL schemes.
- [X] T039 Draw charts off the event loop (BUG-001/PERF-001/SPEC-002/SEC-004): in `backend/app/api/reports.py`, add plain `GraphSource`/`ChartSource` inputs and run `_figures` in a worker thread alongside `synthesize_findings`. A non-dict `spec_json` now gives "Chart unavailable" (BUG-008).
- [X] T040 Wide tables fit the page (SPEC-001/BUG-002): cell-aware break points (15+ characters, every 10) in `_wrap_long_tokens`, plus `_mark_wide_tables` (7+ columns, `class="wide"`, 7.5pt). Covered by a layout-overflow test.
- [X] T041 Line-only bar hatches (PERF-002) in `backend/app/services/charts.py`. A 3-series bar chart went from 389 ms / 212 KB to 65 ms / 17 KB.
- [X] T042 Render limits (SEC-003/PERF-003):
  - body, table-row and equation caps in `pdf_report.py`;
  - `max_output_tokens=16384` in `report_synthesis.py`. That is 16 k, not the planned 8 k, because thinking tokens count toward the budget.
  - `_in_render_slot` with **1** slot, not the planned 2: measured, 4 renders took 1.8 s one at a time and 2.7 s with two slots;
  - a 90 s timeout in `api/reports.py`.
  
  Results: the PoCs' 20 KB equation went from 62 s to 0.21 s, the 3,000-row table from 22.6 s to 1.9 s, and the SVG `<use>` bomb from 110 s to 0.06 s.
- [X] T043 Render-thread follow-ups from the re-check (`qa-reports/2026-10-19-recheck/README.md`), in `backend/app/api/reports.py` and `pdf_report.py`:
  - a dedicated one-thread `_RENDER_POOL` replaces the semaphore, so queued work no longer parks default-executor threads (PERF-010);
  - each chart is its own job, and a report without charts never queues (PERF-011);
  - at most 20 figures with a "N more charts not shown" note, and a 60 s chart-step deadline that falls back to "Chart unavailable" instead of a 500 (PERF-012);
  - caption `source` links only for http(s) URLs (part of SEC-005).

  Results (host, bench17/18): during a burst of 12 downloads, an unrelated `to_thread` call waited at most 144 ms instead of 2.3 s; 12 heavy reports at once all succeeded (previously 1 failed), slowest 48 s instead of 56 s; a light report started just after a 20-chart one took +0.03 s instead of +1.36 s.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on T001. T004 and T005 can run in parallel. T006 → T007 → T008 → T009 run in order, because they touch the same module or depend on the new signature.
- **US1 (Phase 3)**: depends on Phase 2.
- **US2 (Phase 4)**: depends on Phase 2. It only needs the T007 shell, so it doesn't strictly need US1. In practice it runs after US1, because both edit `REPORT_CSS` and `pdf_report.py`.
- **US3 (Phase 5)**: depends on Phase 2 (T005 and T008). It is independent of US1 and US2 in behaviour, but shares `pdf_report.py` with them.
- **Polish (Phase 6)**: T030–T032 can start once US1 is done. T033 only after T005 and T007 (all ReportLab use gone). T034–T037 last.

### Story completion order

US1 (P1, MVP) → US2 (P2) → US3 (P3). The stories don't depend on each other functionally, but they edit the same renderer module, so they run one after another.

### Within each story

- Write the tests first and confirm they fail (T010–T014, T020–T021, T025–T026).
- `findings_to_html` stages in pipeline order: parse (T015), then maths (T016), then sanitise (T017), then CSS (T018).
- Run the story's tests and the visual check at the end of each phase (T019, T024, T029).

### Parallel opportunities

- Phase 1: T002 ∥ T003, after T001.
- Phase 2: T004 ∥ T005 (different files: `wcl_agent/benchmark.py` and `charts.py`).
- US1 tests: T010 ∥ T011 ∥ T012 ∥ T013 ∥ T014 (fixtures, plus independent test functions in one file that don't conflict when written in separate blocks).
- US2 tests: T020 ∥ T021 (different test files).
- US3: T025 ∥ T026 (different test files), and T027 (`charts.py`) ∥ T028 (`pdf_report.py`).
- Polish: T031 ∥ T032.

---

## Parallel Example: User Story 1

```bash
# Fixtures and tests at the same time:
Task: "T010 Hand-written edge-case corpus in backend/tests/fixtures/findings/"
Task: "T011 Export ≥6 real findings docs to backend/tests/fixtures/findings/real-*.md"
Task: "T012 findings_to_html unit tests in backend/tests/test_pdf_report.py"
Task: "T014 Fetch-lockdown test in backend/tests/test_pdf_report.py"
```

## Parallel Example: User Story 3

```bash
Task: "T027 Shared print style in backend/app/services/charts.py"
Task: "T028 Charts section + captions in backend/app/services/pdf_report.py"
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1, then Phase 2. The app then renders through WeasyPrint end to end.
2. Phase 3 (US1). Clean, safe report text. **Stop and validate** with the corpus test and a real download.
3. This alone fixes the defect named in the ticket ("markers visible") and could ship.

### Incremental delivery

1. US1: clean text (stories 109 and 108).
2. US2: the document layout (story 108).
3. US3: the charts (story 110).
4. Polish: drop ReportLab and `markdown`, docs, image check, live check, board to Under Review.

---

## Notes

- `[P]` means different files and no dependency on unfinished tasks. The `[Story]` label maps a task to a user story in spec.md.
- Keep the endpoints byte-for-byte compatible in their headers, file names and error `detail` strings (contracts/report-endpoints.md).
- Never let one bad chart or one bad equation fail a whole report. Never return a partial PDF.
- Commit after each phase checkpoint. Don't push (owner preference).
