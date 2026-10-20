"""PDF report rendering (US5, feature 017).

Turns a findings document (Markdown from ``report_synthesis``) plus its charts into a
PDF: Markdown → sanitised HTML → print CSS → WeasyPrint. Pure/synchronous and CPU-bound
— the caller runs ``render_report_pdf`` via ``asyncio.to_thread`` so it never blocks the
event loop. No database access and no network or file fetches happen here: the endpoint
gathers plain data, and WeasyPrint may only load ``data:`` URLs.
"""

from __future__ import annotations

import base64
import html
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

import nh3
from markdown_it import MarkdownIt
from matplotlib.figure import Figure
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from weasyprint import CSS, HTML
from weasyprint.urls import URLFetcher

from .charts import figure_to_svg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportFigure:
    """One chart in the Charts section; ``svg=None`` means it couldn't be drawn."""

    title: str
    svg: bytes | None
    source_url: str = ""


@dataclass(frozen=True)
class ReportDocument:
    """Everything the renderer needs for one report (see data-model.md)."""

    title: str
    scope: Literal["conversation", "message"]
    generated_at: datetime
    body_markdown: str
    question: str | None = None
    partial: bool = False
    figures: tuple[ReportFigure, ...] = ()
    figures_omitted: int = 0


def _unwrap_latex_text(expr: str) -> str:
    """Reduce a bit of LaTeX to plain readable text (fallback for untypesettable maths).

    Unwraps ``\\text{...}``/``\\mathrm{...}``, drops thin-space commands, and strips a
    few common wrappers so a formula still reads legibly.
    """
    s = expr
    s = re.sub(r"\\(?:text|mathrm|mathit|operatorname)\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\d?frac\{([^}]*)\}\{([^}]*)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\[,;:! ]", " ", s)
    s = _LATEX_SYMBOL_RE.sub(lambda m: _LATEX_SYMBOLS[m.group(0)], s)
    s = re.sub(r"\\[A-Za-z]+", "", s)  # any other command: keep only its arguments
    s = re.sub(r"[{}\\]", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()


_LATEX_SYMBOLS = {
    "\\longrightarrow": "→", "\\rightarrow": "→", "\\to": "→", "\\Rightarrow": "⇒",
    "\\leftarrow": "←", "\\cdot": "·", "\\times": "×", "\\approx": "≈", "\\leq": "≤",
    "\\geq": "≥", "\\neq": "≠", "\\pm": "±", "\\%": "%",
}  # fmt: skip
# Whole command names only, so "\to" never eats the start of "\top" or "\tau".
_LATEX_SYMBOL_RE = re.compile(
    "|".join(re.escape(c) + r"(?![A-Za-z])" for c in sorted(_LATEX_SYMBOLS, key=len, reverse=True))
)


def _svg_data_uri(svg: bytes) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")


def _math_html(latex: str, *, display: bool) -> str:
    """Typeset one equation as an inline SVG image, or fall back to plain text (FR-004).

    Uses the object-oriented ``Figure`` API (no pyplot global state), since reports
    render concurrently in worker threads.
    """
    fig = Figure(figsize=(0.01, 0.01))
    fig.text(0, 0, f"${latex}$", fontsize=12.5 if display else 10)
    try:
        svg = figure_to_svg(fig, pad_inches=0.02)
    except Exception:  # noqa: BLE001 - mathtext can't parse every LaTeX; fall back to text
        return f"<em>{html.escape(_unwrap_latex_text(latex))}</em>"
    cls = "math-block" if display else "math-inline"
    return f'<img class="{cls}" src="{_svg_data_uri(svg)}" alt="">'


# Equations are typeset by the renderer itself and swapped in after sanitising, so the
# only images WeasyPrint ever sees are ours (model-supplied images become text).
_MATH_OPEN, _MATH_CLOSE = "\ue000", "\ue001"
_MATH_SLOT = re.compile(f"{_MATH_OPEN}(\\d+){_MATH_CLOSE}")
# Render limits (QA SEC-003): mathtext cost grows with equation length.
_MAX_MATH_CHARS = 300
_MAX_MATH_COUNT = 60


def _math_slot(env: dict, latex: str, *, display: bool) -> str:
    slots = env.setdefault("math", [])
    if len(latex) > _MAX_MATH_CHARS or len(slots) >= _MAX_MATH_COUNT:
        markup = f"<em>{html.escape(_unwrap_latex_text(latex))}</em>"
    else:
        markup = _math_html(latex, display=display)
    slots.append(markup)
    return f"{_MATH_OPEN}{len(slots) - 1}{_MATH_CLOSE}"


def _render_math_inline(self, tokens, idx, options, env) -> str:
    return _math_slot(env, tokens[idx].content, display=False)


def _render_math_block(self, tokens, idx, options, env) -> str:
    return f'<p class="math">{_math_slot(env, tokens[idx].content, display=True)}</p>\n'


# CommonMark + GFM tables/strikethrough, task lists, and $…$/$$…$$ maths. Dollar maths
# needs a non-space after the opening $ and no digit after the closing one, so prose
# like "costs $5 and $10" is never treated as maths (FR-005).
_MD = (
    MarkdownIt("commonmark", {"html": True})
    .enable(["table", "strikethrough"])
    .use(tasklists_plugin)
    .use(dollarmath_plugin, allow_space=False, allow_digits=False, double_inline=True)
)
_MD.add_render_rule("math_inline", _render_math_inline)
_MD.add_render_rule("math_inline_double", _render_math_block)
_MD.add_render_rule("math_block", _render_math_block)
_MD.add_render_rule("math_block_label", _render_math_block)

# Raw HTML in model output is honoured only for basic formatting; everything else is
# dropped, never shown as text and never executed or fetched (FR-006).
_ALLOWED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "strong", "em", "b", "i", "s",
    "del", "sup", "sub", "code", "pre", "ul", "ol", "li", "blockquote", "table", "thead",
    "tbody", "tr", "th", "td", "a", "img", "span", "div",
}  # fmt: skip
_ALLOWED_ATTRS = {
    "*": {"class"},
    "a": {"href"},
    "img": {"src", "alt"},
    "ol": {"start"},
    "th": {"style"},
    "td": {"style"},
}
_ALIGN_STYLE = re.compile(r"^\s*text-align:\s*(left|right|center)\s*;?\s*$")
_IMG_TAG = re.compile(r"<img\b[^>]*>")
# Task-list checkboxes become glyphs: WeasyPrint lays form inputs out as blocks.
_TASK_BOX = re.compile(r'<input class="task-list-item-checkbox"( checked="checked")?[^>]*>')
_OL_START = re.compile(r'<ol start="(\d+)">')
_IMG_ATTR = re.compile(r'(src|alt)="([^"]*)"')


def _keep_attribute(element: str, attribute: str, value: str) -> str | None:
    # Table cells may only carry markdown-it's column alignment.
    if attribute == "style":
        return value if _ALIGN_STYLE.match(value) else None
    return value


def _images_to_text(markup: str) -> str:
    """Swap every image the model wrote for its alt text or URL (QA SEC-001/SEC-002).

    Runs after sanitising and before the renderer's own equations are swapped in, so no
    model-supplied image (remote, ``data:`` SVG or raster) ever reaches WeasyPrint.
    """

    def swap(m: re.Match) -> str:
        attrs = dict(_IMG_ATTR.findall(m.group(0)))
        return attrs.get("alt") or attrs.get("src", "")

    return _IMG_TAG.sub(swap, markup)


def _task_box(m: re.Match) -> str:
    return f'<span class="task-box">{"☑" if m.group(1) else "☐"}</span>'


def _ol_counter(m: re.Match) -> str:
    # WeasyPrint's UA sheet resets list-item without honouring the start attribute.
    start = int(m.group(1))
    return f'<ol start="{start}" style="counter-reset: list-item {start - 1}">'


_TAG_SPLIT = re.compile(r"(<[^>]+>)")
_CELL_TAG = re.compile(r"^<(/?)t[dh][\s>]")
_ZWSP = "\u200b"
# Outside tables only real outliers need help; inside cells medium tokens such as WCL
# report codes would otherwise stop the table shrinking to the page width (FR-011).
_LONG_TOKEN = re.compile(r"\S{30,}")
_LONG_CELL_TOKEN = re.compile(r"\S{15,}")


def _soft_break(token: str, every: int) -> str:
    """Break opportunities in a long token: after URL separators, else every ``every`` chars."""
    t = re.sub(r"([/&?=_.\-])", rf"\1{_ZWSP}", token)
    return re.sub(rf"([^{_ZWSP}]{{{every}}})(?=[^{_ZWSP}])", rf"\1{_ZWSP}", t)


def _wrap_long_tokens(markup: str) -> str:
    """Let long report codes and URLs wrap inside table cells and the margins (FR-011).

    Only text between tags changes, never attributes (so links keep their targets).
    Ordinary words and numbers are untouched, so tables don't break them mid-word.
    """
    parts = _TAG_SPLIT.split(markup)
    in_cell = 0
    for i, part in enumerate(parts):
        if i % 2:  # odd indexes are tags
            if m := _CELL_TAG.match(part):
                in_cell = max(0, in_cell - 1) if m.group(1) else in_cell + 1
            continue
        pattern, every = (_LONG_CELL_TOKEN, 10) if in_cell else (_LONG_TOKEN, 25)
        text = html.unescape(part)
        if pattern.search(text):
            parts[i] = html.escape(pattern.sub(lambda m: _soft_break(m.group(0), every), text), quote=False)
    return "".join(parts)


_TABLE_BLOCK = re.compile(r"<table>(.*?</thead>)", re.DOTALL)
_WIDE_TABLE_COLUMNS = 7


def _mark_wide_tables(markup: str) -> str:
    """Tag tables with many columns so the CSS can set them tighter (FR-011)."""

    def mark(m: re.Match) -> str:
        wide = m.group(1).count("<th") >= _WIDE_TABLE_COLUMNS
        return ('<table class="wide">' if wide else "<table>") + m.group(1)

    return _TABLE_BLOCK.sub(mark, markup)


# Render limits (QA SEC-003): real findings are well under 10 k characters.
_MAX_BODY_CHARS = 60_000
_MAX_TABLE_ROWS = 200
_SHORTENED_NOTE = "*Report shortened: the findings were too long to print in full.*"


def _cap_markdown(markdown: str) -> str:
    """Bound the work one report can cause: body length and rows per table."""
    if len(markdown) > _MAX_BODY_CHARS:
        cut = markdown.rfind("\n\n", 0, _MAX_BODY_CHARS)
        markdown = markdown[: cut if cut > 0 else _MAX_BODY_CHARS] + f"\n\n{_SHORTENED_NOTE}\n"
    out: list[str] = []
    run = 0  # consecutive table lines; the first two are the header and separator
    dropped = 0
    for line in markdown.splitlines():
        if line.lstrip().startswith("|"):
            run += 1
            if run > _MAX_TABLE_ROWS + 2:
                dropped += 1
                continue
        else:
            if dropped:
                out.append(f"| … {dropped} more rows not shown |")
            run = dropped = 0
        out.append(line)
    if dropped:
        out.append(f"| … {dropped} more rows not shown |")
    return "\n".join(out)


def findings_to_html(markdown: str) -> str:
    """Convert findings Markdown to sanitised HTML for the report body."""
    env: dict = {}
    source = _cap_markdown(markdown.replace(_MATH_OPEN, "").replace(_MATH_CLOSE, ""))
    clean = nh3.clean(
        _TASK_BOX.sub(_task_box, _MD.render(source, env)),
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        attribute_filter=_keep_attribute,
        clean_content_tags={"script", "style", "iframe", "object", "embed", "svg", "math"},
        url_schemes={"http", "https", "mailto"},
        link_rel=None,
    )
    markup = _mark_wide_tables(_OL_START.sub(_ol_counter, _images_to_text(clean)))
    slots = env.get("math", [])
    markup = _MATH_SLOT.sub(lambda m: slots[int(m.group(1))], markup)
    return _wrap_long_tokens(markup)


# One clean, neutral style with tavern-brown accents only (clarify Q2, FR-013/014).
_FONTS = '"DejaVu Sans", "Noto Sans CJK SC", "Noto Color Emoji", sans-serif'
_ACCENT = "#4b2e1e"

REPORT_CSS = f"""
@page {{
  size: A4;
  margin: 20mm 18mm 18mm;
  @top-center {{ content: string(title); font-family: {_FONTS}; font-size: 8pt; color: #777; }}
  @bottom-right {{
    content: "Page " counter(page) " of " counter(pages);
    font-family: {_FONTS}; font-size: 8pt; color: #777;
  }}
}}
@page :first {{ @top-center {{ content: none; }} }}

html {{ background: #fff; }}
body {{ font-family: {_FONTS}; font-size: 10pt; line-height: 1.45; color: #1f1f1f;
        overflow-wrap: break-word; }}
a {{ color: #2b5d8a; }}

/* Title block */
.title-block {{ border-bottom: 1.5pt solid {_ACCENT}; padding-bottom: 6pt; margin-bottom: 12pt; }}
.report-title {{ string-set: title content(); color: {_ACCENT}; font-size: 20pt; margin: 0 0 4pt; }}
.meta {{ color: #555; font-size: 9pt; margin: 0; }}
.question {{ margin: 8pt 0 0; font-style: italic; }}
.partial-note {{ border: 0.75pt solid #b8a07e; background: #f3ece0; padding: 4pt 8pt; font-size: 9pt; }}

/* Headings stay with what follows them (FR-010) */
h1, h2, h3, h4 {{ color: {_ACCENT}; line-height: 1.2; break-after: avoid; }}
h1 {{ font-size: 16pt; margin: 14pt 0 6pt; }}
h2 {{ font-size: 13.5pt; margin: 14pt 0 5pt; }}
h3 {{ font-size: 11.5pt; margin: 10pt 0 4pt; }}
h4 {{ font-size: 10pt; margin: 8pt 0 3pt; }}
p {{ margin: 0 0 6pt; orphans: 2; widows: 2; }}
tr, figure, pre, blockquote, p.math {{ break-inside: avoid; }}
thead {{ display: table-header-group; }}

/* Charts section (FR-012) */
.charts {{ break-before: page; }}
figure {{ margin: 0 0 14pt; }}
figure img {{ width: 100%; }}
figcaption {{ font-size: 9pt; color: #444; margin-top: 3pt; }}
.charts-omitted {{ font-style: italic; color: #777; }}
.chart-unavailable {{ font-style: italic; color: #777; border: 0.75pt dashed #b8a07e;
                      padding: 18pt; text-align: center; margin: 0; }}
th {{ background: {_ACCENT}; color: #fff; text-align: left; }}
tbody tr:nth-child(even) {{ background: #f3ece0; }}
"""

REPORT_CSS += """
/* Content elements (US1) */
ul, ol { padding-left: 16pt; margin: 4pt 0 6pt; }
li { margin: 1.5pt 0; }
li > ul, li > ol { margin: 1pt 0; }
ul.contains-task-list { padding-left: 4pt; }
li.task-list-item { list-style: none; }
span.task-box { margin-right: 4pt; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt;
       background: #f2f2f2; padding: 0 2pt; border-radius: 2pt; }
pre { font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; white-space: pre-wrap;
      background: #f2f2f2; padding: 6pt 8pt; border-radius: 3pt; }
pre code { background: none; padding: 0; }
blockquote { margin: 6pt 0; padding: 2pt 0 2pt 10pt; border-left: 3pt solid #b8a07e; color: #444; }
hr { border: none; border-top: 0.75pt solid #b8a07e; margin: 10pt 0; }
img.math-inline { vertical-align: middle; }
p.math { text-align: center; margin: 8pt 0; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt; font-size: 9pt; }
th, td { border: 0.5pt solid #b8a07e; padding: 3pt 5pt; vertical-align: top; }
table.wide { font-size: 7.5pt; }
table.wide th, table.wide td { padding: 2pt 3pt; }
"""

_FETCHER = URLFetcher(allowed_protocols={"data"})


def _charts_html(figures: tuple[ReportFigure, ...], omitted: int = 0) -> str:
    """The Charts section after the findings, numbered by position (FR-012, FR-015/016)."""
    if not figures:
        return ""
    parts = ['<section class="charts"><h2>Charts</h2>']
    for n, fig in enumerate(figures, 1):
        if fig.svg is not None:
            body = f'<img src="{_svg_data_uri(fig.svg)}" alt="">'
        else:
            body = '<p class="chart-unavailable">Chart unavailable</p>'
        caption = f"Figure {n} — {html.escape(fig.title)}"
        if urlsplit(fig.source_url).scheme in {"http", "https"}:  # QA SEC-005
            caption += f' · <a href="{html.escape(fig.source_url)}">source</a>'
        parts.append(f"<figure>{body}<figcaption>{caption}</figcaption></figure>")
    if omitted:
        parts.append(f'<p class="charts-omitted">{omitted} more chart{"s" * (omitted != 1)} not shown.</p>')
    parts.append("</section>")
    return "".join(parts)


_SCOPE_LABELS = {"conversation": "Whole conversation", "message": "Single answer"}


def _title_block(doc: ReportDocument) -> str:
    """Title, scope, generation time and (single answer) the question — all escaped (FR-008)."""
    when = doc.generated_at.strftime("%Y-%m-%d %H:%M")
    parts = [
        '<header class="title-block">',
        f'<h1 class="report-title">{html.escape(doc.title)}</h1>',
        f'<p class="meta">{_SCOPE_LABELS[doc.scope]} · Generated {when} UTC</p>',
    ]
    if doc.scope == "message" and doc.question:
        parts.append(f'<blockquote class="question">{html.escape(doc.question)}</blockquote>')
    parts.append("</header>")
    if doc.partial:
        parts.append('<p class="partial-note">Interrupted — partial answer</p>')
    return "".join(parts)


def _document_html(doc: ReportDocument) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(doc.title)}</title></head><body>"
        f"{_title_block(doc)}"
        f'<main class="findings">{findings_to_html(doc.body_markdown)}</main>'
        f"{_charts_html(doc.figures, doc.figures_omitted)}"
        "</body></html>"
    )


def render_report_pdf(doc: ReportDocument) -> bytes:
    """Render the report to PDF bytes. Raises on failure; never returns a partial file."""
    started = time.perf_counter()
    rendered = HTML(string=_document_html(doc), base_url=None, url_fetcher=_FETCHER).render(
        stylesheets=[CSS(string=REPORT_CSS)]
    )
    pdf = rendered.write_pdf()
    logger.info(
        "pdf rendered scope=%s pages=%d figures=%d ms=%d",
        doc.scope, len(rendered.pages), len(doc.figures), (time.perf_counter() - started) * 1000,
    )  # fmt: skip
    return pdf
