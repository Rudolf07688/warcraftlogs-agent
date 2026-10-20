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
import itertools
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from urllib.request import url2pathname

import nh3
from markdown_it import MarkdownIt
from matplotlib.figure import Figure
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher

from . import report_theme as theme
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
    fig.text(0, 0, f"${latex}$", fontsize=12.5 if display else 10, color=theme.CREAM)
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


# The only classes kept from the model's HTML: markdown-it's own task-list markup. The
# report components' classes are added after sanitising, so they are always the
# renderer's (QA SEC-006).
_MODEL_CLASSES = {"contains-task-list", "task-list-item", "task-list-item-checkbox", "task-box"}


def _keep_attribute(element: str, attribute: str, value: str) -> str | None:
    # Table cells may only carry markdown-it's column alignment.
    if attribute == "style":
        return value if _ALIGN_STYLE.match(value) else None
    if attribute == "class":
        return " ".join(c for c in value.split() if c in _MODEL_CLASSES) or None
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


# --- Report components ---------------------------------------------------------------
# The synthesis prompt asks for these in plain Markdown; each pass below turns one into
# renderer-owned markup after sanitising. Content that doesn't follow the convention
# stays an ordinary list, quote or table.

_GLANCE = re.compile(r"(<h2>At a Glance</h2>\s*)<ul>\n(.*?)</ul>", re.DOTALL | re.IGNORECASE)
_GLANCE_ITEM = re.compile(r"<li>(?:<strong>(.*?):?</strong>:?\s*)?(.*?)</li>", re.DOTALL)
_KPI_NOTE = re.compile(r"^(.*?)\s*\((.*)\)$", re.DOTALL)


def _kpi_cards(markup: str) -> str:
    """``## At a Glance`` + ``- **Label:** value (note)`` items become KPI cards."""

    def card(m: re.Match) -> str:
        label, value = m.group(1) or "", m.group(2).strip()
        note = ""
        if n := _KPI_NOTE.match(value):
            value, note = n.group(1), n.group(2)
        return (
            f'<div class="kpi"><span class="kpi-value">{value}</span>'
            f'<span class="kpi-label">{label}</span>'
            + (f'<span class="kpi-note">{note}</span>' if note else "")
            + "</div>"
        )

    def grid(m: re.Match) -> str:
        if "<ul" in m.group(2) or "<ol" in m.group(2):  # nested lists: leave as a list
            return m.group(0)
        return f'{m.group(1)}<div class="kpis">{_GLANCE_ITEM.sub(card, m.group(2)).replace(chr(10), "")}</div>'

    return _GLANCE.sub(grid, markup)


_CALLOUT = re.compile(r"<blockquote>\s*<p>\[!(TIP|NOTE|WARNING)\]\s*(?:</p>\s*<p>)?")
_CALLOUT_LABELS = {"TIP": "Key takeaway", "NOTE": "Note", "WARNING": "Caveat"}


def _callouts(markup: str) -> str:
    """GitHub-style ``> [!TIP]`` / ``[!NOTE]`` / ``[!WARNING]`` quotes become callout boxes."""

    def box(m: re.Match) -> str:
        kind = m.group(1)
        return (
            f'<blockquote class="callout callout-{kind.lower()}">'
            f'<p class="callout-label">{_CALLOUT_LABELS[kind]}</p><p>'
        )

    return _CALLOUT.sub(box, markup)


_TABLE = re.compile(r"<table\b[^>]*>.*?</table>", re.DOTALL)
_ROW = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_CELL = re.compile(r"<(t[dh])((?: style=\"[^\"]*\")?)>(.*?)</\1>", re.DOTALL)
_NUMBER = re.compile(r"^[~≈<>+±▲▼−–-]?\s*\d[\d.,:]*\s*(?:%|[kKMB]|ms|s|m|x|×)?$")
_BLANK_CELLS = {"", "—", "–", "-", "n/a", "N/A"}


def _cell_text(inner: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()


def _is_number(text: str) -> bool:
    # A trailing note such as "12.30% (92 procs)" doesn't stop a cell counting as numeric.
    return bool(_NUMBER.match(re.sub(r"\s*\(.*\)$", "", text)))


def _numeric_columns(markup: str) -> str:
    """Right-align table columns that hold only numbers (tabular figures, ``class="num"``).

    A column alignment the model set explicitly is kept; its inline style wins in the CSS.
    """

    def table(m: re.Match) -> str:
        rows = [_CELL.findall(r) for r in _ROW.findall(m.group(0))]
        numeric = set()
        for col in range(max((len(r) for r in rows), default=0)):
            texts = [_cell_text(r[col][2]) for r in rows[1:] if col < len(r)]
            filled = [t for t in texts if t not in _BLANK_CELLS]
            if filled and all(map(_is_number, filled)):
                numeric.add(col)
        if not numeric:
            return m.group(0)

        def cell(c: re.Match) -> str:
            return f'<{c.group(1)} class="num"{c.group(2)}>{c.group(3)}</{c.group(1)}>'

        def row(rm: re.Match) -> str:
            col = itertools.count()
            return f"<tr>{_CELL.sub(lambda c: cell(c) if next(col) in numeric else c.group(0), rm.group(1))}</tr>"

        return _ROW.sub(row, m.group(0))

    return _TABLE.sub(table, markup)


_TIMELINE_ITEM = re.compile(r"<li><code>(\d{1,2}:\d{2}(?::\d{2})?)</code>\s*(?:[:—–-]\s*)?")


def _timeline(markup: str) -> str:
    """List items that open with a backticked ``mm:ss`` become timeline rows."""
    return _TIMELINE_ITEM.sub(r'<li class="tl"><span class="tl-time">\1</span>', markup)


_ACTIONS = re.compile(r"(<h2>[^<]*Recommendation[^<]*</h2>\s*)<ol\b", re.IGNORECASE)


def _action_list(markup: str) -> str:
    """The numbered list under Recommendations becomes a list of action rows."""
    return _ACTIONS.sub(r'\1<ol class="actions"', markup)


def _components(markup: str) -> str:
    return _action_list(_timeline(_numeric_columns(_callouts(_kpi_cards(markup)))))


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
    markup = _components(_mark_wide_tables(_OL_START.sub(_ol_counter, _images_to_text(clean))))
    slots = env.get("math", [])
    markup = _MATH_SLOT.sub(lambda m: slots[int(m.group(1))], markup)
    return _wrap_long_tokens(markup)


# The chat's look (owner's choice 2026-10-20): the "Tavern Hearth" theme of the agent
# messages, dark page included. Cinzel headings and Alegreya Sans body ship with the app
# (OFL, assets/fonts) so host and container render alike. Emoji come from fontconfig
# fallback: naming an emoji font here makes Pango 1.56 draw digits, '#' and '*' as keycaps.
_FONT_DIR = (Path(__file__).resolve().parent.parent / "assets" / "fonts").resolve()
_FONTS = '"Alegreya Sans", "DejaVu Sans", "Noto Sans CJK SC", sans-serif'
_DISPLAY = '"Cinzel", "DejaVu Serif", serif'
_FONT_FACES = (
    ("Cinzel", "Cinzel-Variable.ttf", "400 900", "normal"),
    ("Alegreya Sans", "AlegreyaSans-Regular.ttf", "400", "normal"),
    ("Alegreya Sans", "AlegreyaSans-Italic.ttf", "400", "italic"),
    ("Alegreya Sans", "AlegreyaSans-Medium.ttf", "500", "normal"),
    ("Alegreya Sans", "AlegreyaSans-Bold.ttf", "700", "normal"),
)
_FONT_FACE_CSS = "".join(
    f'@font-face {{ font-family: "{family}"; src: url("{(_FONT_DIR / file).as_uri()}"); '
    f"font-weight: {weight}; font-style: {style}; }}\n"
    for family, file, weight, style in _FONT_FACES
)
_T = theme

REPORT_CSS = _FONT_FACE_CSS + f"""
@page {{
  size: A4;
  margin: 20mm 18mm 18mm;
  background: {_T.OAK};
  @top-center {{ content: string(title); font-family: {_FONTS}; font-size: 8pt; color: {_T.TAN}; }}
  @bottom-right {{
    content: "Page " counter(page) " of " counter(pages);
    font-family: {_FONTS}; font-size: 8pt; color: {_T.TAN};
  }}
}}
@page :first {{ @top-center {{ content: none; }} }}

html {{ background: {_T.OAK}; }}
body {{ font-family: {_FONTS}; font-size: 10.5pt; line-height: 1.55; color: {_T.CREAM};
        overflow-wrap: break-word; }}
a {{ color: {_T.GLOW}; text-decoration: underline; }}
strong, b {{ font-weight: 700; color: #f6efe0; }}

/* Title block */
.title-block {{ border-bottom: 0.75pt solid {_T.GOLD}; padding-bottom: 8pt; margin-bottom: 14pt; }}
.report-title {{ string-set: title content(); font-family: {_DISPLAY}; font-weight: 700;
                 letter-spacing: 0.03em; color: {_T.GLOW}; font-size: 20pt; margin: 0 0 4pt; }}
.meta {{ color: {_T.TAN}; font-size: 9pt; margin: 0; }}
.question {{ margin: 10pt 0 0; padding: 6pt 10pt; background: {_T.CARD}; border-left: 3pt solid {_T.GOLD};
             border-radius: 0 6pt 6pt 0; font-style: italic; color: {_T.CREAM}; }}
.partial-note {{ border-left: 3pt solid {_T.EMBER}; background: {_T.CARD}; padding: 5pt 10pt;
                 border-radius: 0 6pt 6pt 0; font-size: 9pt; color: {_T.CREAM}; }}

/* Headings stay with what follows them (FR-010) */
h1, h2, h3, h4 {{ font-family: {_DISPLAY}; letter-spacing: 0.03em; line-height: 1.25; break-after: avoid; }}
h1 {{ font-size: 16pt; color: {_T.GLOW}; margin: 16pt 0 6pt; }}
h2 {{ font-size: 13pt; font-weight: 700; color: {_T.GOLD}; margin: 18pt 0 6pt; }}
h3 {{ font-size: 11pt; font-weight: 600; color: {_T.CREAM}; margin: 12pt 0 4pt; }}
h4 {{ font-size: 10pt; font-weight: 600; color: {_T.TAN}; margin: 10pt 0 3pt; }}
p {{ margin: 0 0 6pt; orphans: 2; widows: 2; }}
tr, figure, pre, blockquote, p.math, .kpi, li.tl {{ break-inside: avoid; }}
thead {{ display: table-header-group; }}

/* Content elements (US1) */
ul, ol {{ padding-left: 16pt; margin: 4pt 0 8pt; }}
li {{ margin: 2pt 0; }}
li::marker {{ color: {_T.GOLD}; }}
li > ul, li > ol {{ margin: 1pt 0; }}
ul.contains-task-list {{ padding-left: 4pt; }}
li.task-list-item {{ list-style: none; }}
span.task-box {{ margin-right: 4pt; color: {_T.GOLD}; }}
code {{ font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; color: {_T.CREAM};
        background: {_T.OAK}; border: 0.75pt solid {_T.BORDER}; padding: 0 3pt; border-radius: 3pt; }}
pre {{ font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; white-space: pre-wrap;
       background: {_T.OAK}; border: 0.75pt solid {_T.BORDER}; padding: 8pt 10pt; border-radius: 6pt; }}
pre code {{ background: none; border: none; padding: 0; }}
blockquote {{ margin: 8pt 0; padding: 2pt 0 2pt 10pt; border-left: 3pt solid {_T.GOLD}; color: {_T.TAN}; }}
hr {{ border: none; border-top: 0.75pt solid {_T.BORDER}; margin: 12pt 0; }}
img.math-inline {{ vertical-align: middle; }}
p.math {{ text-align: center; margin: 8pt 0; }}

/* Tables: the chat's rounded cards (Streamdown) */
table {{ width: 100%; border-collapse: separate; border-spacing: 0; margin: 8pt 0 12pt; font-size: 9pt;
         background: {_T.CARD}; border: 0.75pt solid {_T.BORDER}; border-radius: 6pt; }}
th, td {{ padding: 4pt 7pt; vertical-align: top; text-align: left; }}
th {{ background: {_T.RAISED}; color: {_T.CREAM}; font-weight: 700; border-bottom: 0.75pt solid {_T.BORDER}; }}
th:first-child {{ border-top-left-radius: 6pt; }}
th:last-child {{ border-top-right-radius: 6pt; }}
td {{ border-top: 0.5pt solid {_T.BORDER}; }}
tbody tr:first-child td {{ border-top: none; }}
tbody tr:nth-child(even) td {{ background: {_T.ZEBRA}; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
table.wide {{ font-size: 7.5pt; }}
table.wide th, table.wide td {{ padding: 2.5pt 3.5pt; }}

/* Report components (see _components) */
.kpis {{ display: flex; flex-wrap: wrap; gap: 6pt; margin: 4pt 0 12pt; }}
.kpi {{ flex: 1 1 28%; background: {_T.CARD}; border: 0.75pt solid {_T.BORDER}; border-radius: 6pt;
        padding: 7pt 9pt; }}
.kpi-value, .kpi-label, .kpi-note {{ display: block; }}  /* block, not flex: wrapped lines grow */
.kpi-value {{ font-size: 17pt; font-weight: 700; line-height: 1.1; color: {_T.GLOW};
              font-variant-numeric: tabular-nums; }}
.kpi-label {{ font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
              color: {_T.TAN}; margin-top: 3pt; }}
.kpi-note {{ font-size: 8pt; color: {_T.TAN}; }}
.callout {{ background: {_T.CARD}; border-left: 3pt solid {_T.GOLD}; border-radius: 0 6pt 6pt 0;
            padding: 7pt 11pt; color: {_T.CREAM}; }}
.callout-warning {{ border-left-color: {_T.EMBER}; }}
.callout-label {{ font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em;
                  color: {_T.GOLD}; margin-bottom: 2pt; }}
.callout-warning .callout-label {{ color: {_T.EMBER}; }}
li.tl {{ list-style: none; margin: 0; padding: 3pt 0; border-bottom: 0.5pt solid {_T.BORDER}; }}
.tl-time {{ display: inline-block; width: 32pt; font-weight: 700; color: {_T.GOLD};
            font-variant-numeric: tabular-nums; }}
ol.actions {{ list-style: none; padding-left: 0; counter-reset: act; }}
ol.actions > li {{ counter-increment: act; position: relative; padding: 5pt 0 5pt 24pt; margin: 0;
                   border-bottom: 0.5pt solid {_T.BORDER}; }}
ol.actions > li::before {{ content: counter(act); position: absolute; left: 0; top: 5pt; width: 15pt;
                           height: 15pt; border-radius: 7.5pt; background: {_T.GOLD}; color: {_T.ON_GOLD};
                           font-size: 8pt; font-weight: 700; text-align: center; line-height: 15pt; }}
ol.actions > li > strong:first-child {{ display: block; color: {_T.CREAM}; }}

/* Charts section (FR-012) */
.charts {{ break-before: page; }}
figure {{ margin: 0 0 16pt; padding: 8pt; background: {_T.CARD}; border: 0.75pt solid {_T.BORDER};
          border-radius: 6pt; }}
figure img {{ width: 100%; }}
figcaption {{ font-size: 9pt; color: {_T.TAN}; margin-top: 4pt; }}
.charts-omitted {{ font-style: italic; color: {_T.TAN}; }}
.chart-unavailable {{ font-style: italic; color: {_T.TAN}; border: 0.75pt dashed {_T.BORDER};
                      border-radius: 6pt; padding: 18pt; text-align: center; margin: 0; }}
"""


class _ReportFetcher(URLFetcher):
    """Renderer-owned resources only: ``data:`` (equations, charts) and the bundled fonts.

    ``file:`` is allowed solely for paths that resolve inside ``assets/fonts`` (traversal
    is resolved first); there is no base URL, so relative URLs never resolve (R6).
    """

    def fetch(self, url, headers=None):
        if url.lower().startswith("file:"):
            path = Path(url2pathname(urlsplit(url).path)).resolve()
            if not path.is_relative_to(_FONT_DIR):
                raise ValueError(f"file URL outside the report fonts: {url}")
        return super().fetch(url, headers)


_FETCHER = _ReportFetcher(allowed_protocols={"data", "file"})


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


def _layout(document_html: str):
    """Lay the document out with the report stylesheet and the bundled fonts."""
    fonts = FontConfiguration()  # per render: reports render concurrently in threads
    css = CSS(string=REPORT_CSS, url_fetcher=_FETCHER, font_config=fonts)
    return HTML(string=document_html, base_url=None, url_fetcher=_FETCHER).render(
        stylesheets=[css], font_config=fonts
    )


def render_report_pdf(doc: ReportDocument) -> bytes:
    """Render the report to PDF bytes. Raises on failure; never returns a partial file."""
    started = time.perf_counter()
    rendered = _layout(_document_html(doc))
    pdf = rendered.write_pdf()
    logger.info(
        "pdf rendered scope=%s pages=%d figures=%d ms=%d",
        doc.scope, len(rendered.pages), len(doc.figures), (time.perf_counter() - started) * 1000,
    )  # fmt: skip
    return pdf
