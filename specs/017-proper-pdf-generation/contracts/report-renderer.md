# Contract: Report renderer (`backend/app/services/pdf_report.py`)

The renderer is pure, synchronous and CPU-bound, with no database or network access. Callers run it through `asyncio.to_thread`.

## Public functions

```python
def render_report_pdf(doc: ReportDocument) -> bytes
```
- Returns PDF bytes starting with `b"%PDF"`.
- Raises on any failure. It never returns a partial document, and the API maps the exception to `500 pdf_generation_failed`.
- Deterministic in its content: the same `doc` gives the same text, links and figures.

```python
def findings_to_html(markdown: str) -> str
```
- The pure Markdown-to-sanitised-HTML stage, exported so it can be unit-tested directly. It is used only by `render_report_pdf`.

## Rendering pipeline

0. **Cap** (`_cap_markdown`): the body is cut at 60,000 characters (at a blank line, with a "Report shortened" note), and each table keeps its first 200 rows plus a "… N more rows not shown" row. Private-use characters `\ue000`/`\ue001` are stripped so maths placeholders can't be forged.
1. **Parse**: markdown-it-py (`commonmark` preset, plus `table` and `strikethrough`), with the `tasklists` and `dollarmath` plugins (`allow_space=False`, `allow_digits=False`, `double_inline=True`), and `html=True`.
2. **Maths**: `math_inline` and `math_block` tokens go to matplotlib mathtext and come out as SVG `data:` images, inline or block. Each one is stored in the render's `env` and leaves only a placeholder (`\ue000{n}\ue001`) in the markup; the images are swapped in **after** sanitising. Equations longer than 300 characters, and any after the 60th in a report, use the text fallback, as does anything mathtext can't parse: `<em>{_unwrap_latex_text(src)}</em>`. No `$`, `\` or `{}` from maths syntax ever reaches the output (FR-004).
3. **Sanitise**: nh3 with the allow-list below. Then **every** `img` left (all of them came from the model) is replaced by its alt text, or by the bare link if there is no alt text. That includes `data:` images, so no model-supplied SVG or raster ever reaches WeasyPrint (QA SEC-001/002).
3a. **Post-process**: `ol start` counter fix; tables with 7 or more header cells get `class="wide"`; the maths placeholders are replaced by their images; then long tokens get zero-width break points (text between tags only): 15+ characters inside table cells (after separators, else every 10), 30+ elsewhere (every 25). Numbers and dates stay whole.
4. **Assemble**: title block, then the optional partial note, then the findings body, then the optional Charts section, inside a minimal HTML shell with the report stylesheet.
5. **Render**: `weasyprint.HTML(string=…, base_url=None, url_fetcher=URLFetcher(allowed_protocols={"data"})).write_pdf(stylesheets=[CSS(string=REPORT_CSS)])`.

### Sanitiser allow-list (nh3)

| Item | Allowed |
|---|---|
| Tags | `h1`–`h6` `p` `br` `hr` `strong` `em` `b` `i` `s` `del` `sup` `sub` `code` `pre` `ul` `ol` `li` `blockquote` `table` `thead` `tbody` `tr` `th` `td` `a` `img` `span` `div` (task-list checkboxes become ☑/☐ glyphs before sanitising, so `input` is not allowed) |
| Attributes | `a[href]`; `img[src alt]`; `th/td[style]`, limited to `text-align` (markdown-it's column alignment); `ol[start]`; `*[class]` |
| URL schemes | `http`, `https` and `mailto`. `data:` is not allowed, so neither links nor images keep it; images are turned into text in step 3 anyway. |
| Dropped with their content | `script`, `style`, `iframe`, `object`, `embed`, `svg` (raw), HTML comments |

### Fetch policy

`_FETCHER` (`_ReportFetcher`) fetches only `data:` URLs, which the renderer's own images (equations, charts) use, and `file:` URLs that resolve inside `backend/app/assets/fonts/` (the bundled fonts, loaded by `@font-face`; `../` traversal is resolved before the check). `http:`, `https:`, any other `file:` path and everything else raise inside WeasyPrint, and the resource is skipped. The document has no `base_url`, so relative URLs never resolve (R6).

## Document structure (HTML)

```html
<header class="title-block">
  <h1 class="report-title">{title}</h1>             <!-- string-set: title (running header) -->
  <p class="meta">{Whole conversation | Single answer} · Generated {YYYY-MM-DD HH:MM} UTC</p>
  <blockquote class="question">{question}</blockquote>   <!-- message scope only -->
</header>
<p class="partial-note">Interrupted — partial answer</p> <!-- when partial -->
<main class="findings">{findings_to_html(body_markdown)}</main>
<section class="charts">                             <!-- only when figures -->
  <h2>Charts</h2>
  <figure>
    <img src="data:image/svg+xml;base64,…">  |  <p class="chart-unavailable">Chart unavailable</p>
    <figcaption>Figure {n} — {title} · <a href="{source_url}">source</a></figcaption>   <!-- link only for http(s) source_url -->
  </figure>
  <p class="charts-omitted">{n} more charts not shown.</p>   <!-- when figures_omitted > 0 -->
</section>
```

All interpolated text (`title`, `question` and figure titles) is HTML-escaped. Only `findings_to_html` output goes in unescaped, and it has already been sanitised.

## Stylesheet rules (`REPORT_CSS`)

Behaviour the CSS must provide (FR-008 to FR-014). The exact values are design detail.

| Rule | Purpose |
|---|---|
| `@page { size: A4; margin: ~20mm }`, which also lays out on Letter | FR-011 |
| `@page { @top-center { content: string(title) } }`, with `@page :first` hiding it | Running header from page 2 (FR-009) |
| `@page { @bottom-right { content: "Page " counter(page) " of " counter(pages) } }` | FR-009 |
| `h1–h4 { break-after: avoid }`, `figure, tr, pre, blockquote { break-inside: avoid }` | No orphaned headings or split rows (FR-010) |
| `thead { display: table-header-group }` | Header repeats after a break (FR-010) |
| `table { width: 100%; table-layout: auto }`, cells `overflow-wrap: anywhere`; `pre { white-space: pre-wrap }`; `body { overflow-wrap: anywhere }` | Nothing goes past the margins (FR-011) |
| Fonts bundled in `backend/app/assets/fonts/` (OFL) and loaded with `@font-face` through a per-render `FontConfiguration`: **Cinzel** for the title and headings (0.03em tracking), **Alegreya Sans** for the body. Body stack `"Alegreya Sans", "DejaVu Sans", "Noto Sans CJK SC", sans-serif`; `code, pre`: `"DejaVu Sans Mono"`. **No emoji font in any stack**: Pango 1.56 would draw digits, `#` and `*` as keycaps; emoji come from fontconfig fallback | FR-007 and a consistent style (FR-013) |
| **The chat's "Tavern Hearth" theme, dark page included** (owner's choice 2026-10-20, replacing the earlier white page). Colours are `report_theme` constants, converted from the frontend's oklch tokens: oak page, card-coloured tables and KPI cards, cream text, gold headings, glow-gold title, links and KPI values. Tables are rounded cards with a raised header row and zebra rows. Charts and equations draw in cream on transparent backgrounds | Matches the agent messages in the chat (FR-013, FR-014) |
| Components: `.kpis`/`.kpi` cards, `.callout` (tip/note/warning), `.num` columns (right-aligned, tabular figures), `li.tl` timeline rows, `ol.actions` numbered action rows | Report components (`pdf_report._components`) |
| `.task-list-item { list-style: none }` with the checkbox inline | Fixes the spike gap |
| `.charts { break-before: page }` | Charts start on a new page (FR-012) |

## Chart helpers (`backend/app/services/charts.py`)

```python
def chart_spec_to_svg(spec: ChartSpec) -> bytes        # replaces chart_spec_to_matplotlib
def graph_to_svg(graph_json: dict) -> bytes | None   # moved from pdf_report._graph_image; title goes in the caption
```

- Both use one print style: figure size about 6.5 × 3.2 in, a cycle of (line style, marker) per series so series stay distinguishable in black and white (FR-017), a light grid, a legend only when there is more than one series, and axis labels when set (FR-015).
- The chart title isn't drawn inside the SVG. It goes in the HTML caption.
- `chart_spec_to_svg` raises on bad input. `graph_to_svg` returns `None` when there is no plottable series. The API turns either into `ReportFigure(svg=None)` (FR-016).
- `chart_spec_to_plotly` and the in-chat charts are unchanged.

## Render limits (QA follow-ups, 2026-10-19)

| Limit | Where | Value |
|---|---|---|
| Findings output | `report_synthesis._MAX_OUTPUT_TOKENS` | 16,384 tokens (includes thinking tokens on thinking models) |
| Body length | `pdf_report._MAX_BODY_CHARS` | 60,000 characters, then a "Report shortened" note |
| Table rows | `pdf_report._MAX_TABLE_ROWS` | 200 per table, then "… N more rows not shown" |
| Equations | `pdf_report._MAX_MATH_CHARS` / `_MAX_MATH_COUNT` | 300 characters each, 60 per report; beyond that, plain text |
| Concurrent renders | `api/reports._RENDER_POOL` | One dedicated thread (`ThreadPoolExecutor(max_workers=1)`) runs chart drawing and PDF renders in turn. Each chart is its own job, so a waiting render gets in after at most one chart; a report without charts doesn't queue for charts. Queued jobs live in the pool's work queue, not in default-executor threads (QA PERF-010/011). |
| Figures per report | `api/reports._MAX_FIGURES` | 20, in display order; the Charts section ends with "N more charts not shown" |
| Chart step | `api/reports._CHARTS_TIMEOUT_S` | 60 s deadline for all of a report's charts (queue wait included); charts past it print "Chart unavailable", the report still renders (FR-016) |
| Render timeout | `api/reports._RENDER_TIMEOUT_S` | 90 s including the queue wait, then `500 pdf_generation_failed` (a running job can't be killed; the caps bound how long it can run) |

Chart drawing (`_figures`) runs on the render thread at the same time as the findings model call, never on the event loop (FR-022). Process isolation (a killable subprocess) was left out on purpose: with model images removed and the caps above, the remaining cost grows roughly linearly with capped input.
