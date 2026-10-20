# Research: Proper PDF Generation

All decisions below were checked with a throwaway spike on 2026-10-19: Python 3.14.4, WeasyPrint 70.0, markdown-it-py 4.2.0, mdit-py-plugins 0.6.1, nh3 0.3.7 and matplotlib 3.11.2. The spike rendered a findings document containing every element from FR-002, plus the spec's edge cases (stray HTML, `<script>`, a remote image, currency `$`, a bad equation, a ragged table, a long token, Cyrillic and Latin-extended names, and an emoji). It then extracted the PDF text with pypdf and also rasterised the pages to look at them.

**Spike result**:
- None of `**`, `##`, `|---`, `<br>`, `<b>`, `$$` or `](` is left in the extracted text.
- The `<script>` body is dropped.
- Both links are real link annotations.
- The ragged table row is trimmed and the short row padded.
- The long token and the long code-block line wrap.
- The header, the "Page X of Y" footer and the Charts page break all work.
- The render took **0.35 s** (Markdown and maths 0.09 s, sanitising 0.05 s, PDF 0.21 s).

Three gaps showed up, and the design below fixes each one:
- Task-list checkboxes sat on their own line under a bullet.
- An equation that couldn't be typeset fell back to its raw source (`\badcommand{x}`).
- The page header and footer used the default serif font.

## R1: Rendering engine

- **Decision**: **WeasyPrint** renders an HTML document plus a print stylesheet into a PDF.
- **Rationale**:
  - It supports CSS Paged Media natively. That covers running headers (`string-set`), "page X of Y" (`counter(pages)`), `break-after: avoid` on headings, repeating `thead` and `break-inside: avoid` on rows and figures. Those cover FR-009 to FR-011 with no layout code of our own.
  - It is pure Python on top of Pango and HarfBuzz, so it adds no browser process to the backend container.
  - It is fast: 0.21 s per report in the spike.
  - The URL fetcher can be locked down (see R6).
- **Alternatives considered**:
  - *Headless Chromium (Playwright)*: the same HTML would render KaTeX and Plotly exactly as the chat shows them. But it adds a browser of roughly 300 MB to the image, a subprocess to manage per request, and a much bigger attack surface. Its paged-media support (running headers, `counter(pages)`) is also weaker than WeasyPrint's. Charts and maths can be rendered on the server instead (R4, R5), so we don't need it.
  - *Keep ReportLab and improve the hand-written parser*: this is the approach that has failed three times (todo Phases 1, 3 and 5). Every new Markdown construct needs new parser code, and ReportLab's mini-markup leaks raw text whenever it fails to match.
  - *xhtml2pdf*: built on ReportLab, with weak CSS support (no `counter(pages)` and no running strings).

## R2: Markdown → HTML

- **Decision**: **markdown-it-py**, with the `commonmark` preset plus the `table` and `strikethrough` rules, and two plugins from **mdit-py-plugins**: `tasklists` and `dollarmath`.
- **Rationale**:
  - The parser follows the spec (CommonMark and GFM tables), so it handles nested lists, emphasis inside table cells, link text and ragged table rows correctly. All of those break the current regex parser.
  - `dollarmath` with `allow_space=False, allow_digits=False` leaves "$5 and $10" alone (FR-005) and still recognises `$a^2$`, `$$…$$` and `\[…\]`-style blocks.
  - Custom render rules let us typeset maths ourselves (R4).
  - It is the Markdown engine Jupyter and MyST use, so it is well maintained.
- **Alternatives considered**:
  - *Python-Markdown (`markdown`)*: it's already in `pyproject.toml` but **nothing imports it**. Its tables and nested lists come from extensions with known quirks, such as needing four-space indents for nested lists, which model output often doesn't follow. Its maths support needs a third-party extension. We **remove** the unused dependency instead of reviving it.
  - *mistune*: fast, but its maths and task-list plugins are less mature and its output differs from CommonMark in edge cases.

## R3: Sanitising raw HTML in model output

- **Decision**: Render with `html=True`, then run the HTML through **nh3** with an allow-list:
  - **Allowed tags**: headings, `p`, `br`, `hr`, `strong`, `em`, `b`, `i`, `s`, `del`, `code`, `pre`, lists, `blockquote`, table tags, `a`, `img`, `input`, `span`, `div` and `sup`/`sub`.
  - **Allowed link schemes**: `http`, `https` and `mailto`.
  - **Allowed image source**: our own `data:` URIs only.
- **Rationale**:
  - FR-006 says basic formatting tags MAY be honoured and anything else must be dropped. The `<br>` and `<b>` in the spike were honoured, and `<script>` was dropped together with its contents.
  - nh3 binds to the Rust `ammonia` sanitiser. It is fast (0.05 s) and maintained.
  - **Remote images**: any `img` whose source isn't `data:` is swapped for its alt text, or the bare link, before rendering. That covers the spec edge case and is in line with the open SEC-003 concern.
- **Alternatives considered**:
  - *`html=False`*: raw tags would appear as visible text (`&lt;br&gt;`), which FR-001 forbids.
  - *bleach*: deprecated upstream since 2023.

## R4: Equations

- **Decision**: Typeset maths on the server with **matplotlib mathtext → SVG**, embedded as an inline `data:` image. Inline maths goes in at body-text size with `vertical-align: middle`, and block maths is centred. If mathtext can't parse an equation, fall back to the **existing** `_unwrap_latex_text` helper (moved into the new module) and show the result in italics.
- **Rationale**:
  - WeasyPrint doesn't run JavaScript, so KaTeX can't work, and it doesn't render MathML.
  - matplotlib is already a dependency, and the current PDF already uses mathtext for block equations. Switching from PNG to SVG keeps equations sharp at any zoom.
  - Reusing `_unwrap_latex_text` follows Principle I and fixes the spike's raw-source fallback (FR-004).
  - mathtext covers what the analyst writes in practice: `\text`, `\frac`, sub- and superscripts, `\longrightarrow`, `\times` and `\cdot`.
- **Alternatives considered**:
  - *latex2mathml*: WeasyPrint has no MathML rendering.
  - *A real LaTeX toolchain (dvisvgm)*: hundreds of MB of TeX in the image.
  - *KaTeX through Node at render time*: adds a Node runtime to the backend image.

## R5: Charts

- **Decision**: Keep matplotlib as the PDF chart renderer, but output **SVG** (vector, FR-015) instead of PNG wrapped in a ReportLab `Image`:
  - `charts.py` gains a shared `figure_to_svg(fig) -> bytes` and one shared **print style**: a monochrome-safe cycle of line style and marker per series (FR-017), a light grid, and tavern-brown title and axes accents. Both the agent-chart path and the captured-graph path use them.
  - `chart_spec_to_matplotlib` returns SVG bytes, and its single caller (`pdf_report`) adapts.
  - `_series_from_graph` and the captured-graph drawing move next to it, so there is one chart module.
  - Captions ("Figure N — {title}", plus a source link) become HTML `figcaption`s rather than text baked into the image, so they use the document font and the links can be clicked.
- **Rationale**: This is the smallest change that makes charts sharp, readable in black and white, and visually consistent. It keeps "one ChartSpec, two renderers" (Plotly for the UI, matplotlib for the PDF) and adds no new dependency. Today the chart and graph code has two copies of the plotting boilerplate, and this merges them (Principle I).
- **Alternatives considered**:
  - *Plotly → kaleido static export*: kaleido needs a bundled Chromium, which is the same weight problem as R1.
  - *Charts as HTML/CSS*: not workable for line and area charts.

## R6: Blocking remote and local fetches while rendering

- **Decision**: Pass `url_fetcher=URLFetcher(allowed_protocols={"data"})` to WeasyPrint. This is a built-in option in WeasyPrint 70, which the spike confirmed. Also set no `base_url`.
- **Rationale**:
  - FR-006 says nothing may be fetched while a report is built.
  - Blocking **`file:`** as well as `http(s):` matters. Without it, an `<img src="file:///etc/passwd">` (or a CSS `url()`) in model output could pull server files into the PDF. Allowing `data:` only rules this out, even if the sanitiser ever let such a tag through.
  - Our own CSS is passed as a `stylesheets=[CSS(string=...)]` object, not linked by URL.
- **Alternatives considered**: a custom fetcher function. That API changed in WeasyPrint 70 (`default_url_fetcher` was removed), so the built-in option is simpler and more stable.

## R7: Fonts and character coverage

- **Decision**: Use **DejaVu Sans** for body text, headings, and the page header and footer. It is already installed via `fonts-dejavu-core` and covers Latin-extended, Greek and Cyrillic. Add two fallbacks to the font stack: **Noto Sans CJK** (`fonts-noto-cjk`) for KR, TW and CN realm and character names, and **Noto Color Emoji** (`fonts-noto-color-emoji`). Pango then substitutes per glyph, so missing-glyph boxes don't appear (FR-007 and the emoji edge case). Code uses **DejaVu Sans Mono**.
- **Rationale**: These are system packages on the existing Debian slim base, so no font files go into the repo. WeasyPrint embeds only the glyphs it uses, so PDFs stay small (42 KB in the spike).
- **Cost**: the backend image grows by about 120 MB: Noto CJK is about 90 MB and the Pango/HarfBuzz libraries are about 20 MB. This is logged in the plan's Complexity Tracking. If image size ever matters more than CJK names, `fonts-noto-cjk` is the one line to drop.
- **Alternatives considered**: bundling a web font such as Inter. It looks nicer but adds licence and asset files and needs fallbacks anyway, and DejaVu is legible and neutral, which fits the style decision from the clarify session.

## R8: System libraries in the container

- **Decision**: In `backend/Dockerfile`, add `libpango-1.0-0`, `libpangoft2-1.0-0` and `libharfbuzz-subset0`, plus the R7 fonts. Remove nothing else: matplotlib still needs `libfreetype6` and `libpng16-16`.
- **Rationale**: WeasyPrint's documented runtime requirements on Debian. `python:3.14-slim` is based on Debian trixie, which ships Pango 1.56, above WeasyPrint's minimum of 1.44.
- **Local development**: the host (Ubuntu) already has Pango. The quickstart lists the `apt` line for a machine that doesn't.

## R9: Title block, partial answers and the renderer's signature

- **Decision**: The renderer takes one typed input, the `ReportDocument` dataclass described in data-model.md. It no longer takes the conversation-shaped `messages` list, which both endpoints already reduce to one synthetic agent message.
  - `api/reports.py::_synthesize_and_render` builds a `ReportDocument` with `scope`, `question` and `partial`.
  - The per-message endpoint passes `partial = (msg.status == "partial")`. Today that flag is **lost**, because the synthetic message is always marked `"complete"`. This fixes the spec's "partial answer is marked" edge case.
- **Rationale**: FR-008 needs the scope and the question in the title block, so the signature had to change anyway. A typed input (Principle IV) replaces the plain dicts and makes the renderer easy to test without a database. `render_report_pdf` stays the name and the single entry point. Its only callers are `api/reports.py::_render` (through `asyncio.to_thread`; GitNexus reports this as UNKNOWN because it is passed as a callable reference, so I confirmed it with a text search) and three test modules.

## R10: Timing baseline (for SC-005)

- **Measured 2026-10-19 on the dev host**: the current ReportLab renderer takes **1.81 s** for the spike document with one chart, including matplotlib warm-up. The WeasyPrint pipeline took **0.35 s** without imports. A report request's total time is dominated by the findings rewrite (the LLM call, capped at 60 s), which this feature doesn't touch, so SC-005 ("no slower than today") holds comfortably.
- **Decision**: log one INFO line per report: `pdf rendered scope=… pages=… figures=… ms=…`. It's enough to check SC-005 in the live check without adding metrics plumbing.

## R11: Test strategy

- **Decision**:
  - **Fixture corpus**: `backend/tests/fixtures/findings/` holds 20 or more `.md` findings documents. Some are real ones exported from the local database (agent messages put through the existing synthesis), and the rest are hand-written edge-case files, one per FR-002 element and per spec edge case.
  - **Corpus test**: every fixture renders, its text is extracted with **pypdf** (added to the `test` extra only), and the test asserts that no syntax markers or tags remain (SC-001 and SC-002). It also checks that links appear as URI annotations (SC-003) and that the "Page 1 of N" footer is there (FR-009).
  - **Unit tests**: the HTML stage is tested on its own as a pure function from Markdown to HTML (maths fallback, currency, sanitising, remote image swap, task lists).
  - **Fetch test**: a `file://` image and a CSS `url(http://…)` in input never reach the network or the filesystem (R6).
  - **Existing endpoint tests** (`test_reports.py` and `test_message_report.py`) keep their `%PDF` and fail-closed assertions unchanged (FR-018 and FR-020).
  - Tests that use ReportLab internals (`_markdown_flowables`, `_inline_md_to_rl`, `Image`) are rewritten against the new HTML stage.
- **Manual checks**: page breaks, the visual style and black-and-white printing (SC-004, SC-006 and SC-007) go in quickstart.md, with the old and new PDFs of the same conversation side by side.
