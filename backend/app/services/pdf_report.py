"""PDF report rendering (US5).

Builds a downloadable PDF from a conversation's written analysis plus the graph
JSON captured during the chat. Pure/synchronous and CPU-bound — the caller runs
``render_report_pdf`` via ``asyncio.to_thread`` so it never blocks the event loop.
No database access happens here: the endpoint gathers plain data and passes it in.
"""

from __future__ import annotations

import html
import io
import re
from datetime import datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless backend — no display needed
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _inline_md_to_rl(text: str) -> str:
    """Convert a line of inline markdown to reportlab's mini-HTML markup (escaped)."""
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', out)
    return out


def _ensure_pdf_styles(styles) -> None:
    """Augment the base stylesheet with wrap-friendly body + table-cell styles (US3).

    ``wordWrap="CJK"`` lets long unbroken tokens (report codes, URLs, ability names)
    wrap within the page margins instead of overflowing.
    """
    styles["BodyText"].wordWrap = "CJK"
    if "WclCell" not in styles:
        styles.add(
            ParagraphStyle(
                "WclCell", parent=styles["BodyText"], fontSize=8, leading=10, wordWrap="CJK"
            )
        )
    if "WclCellHeader" not in styles:
        styles.add(
            ParagraphStyle(
                "WclCellHeader",
                parent=styles["WclCell"],
                fontName="Helvetica-Bold",
                textColor=colors.white,
            )
        )
    if "WclQuestion" not in styles:
        styles.add(
            ParagraphStyle(
                "WclQuestion",
                parent=styles["Heading2"],
                textColor=colors.HexColor("#4b2e1e"),
                spaceBefore=12,
                wordWrap="CJK",
            )
        )


def _split_table_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table_separator(line: str) -> bool:
    cells = [c for c in _split_table_cells(line) if c != ""]
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", c) for c in cells)


def _looks_like_table(lines: list[str]) -> bool:
    return (
        len(lines) >= 2
        and "|" in lines[0]
        and _is_table_separator(lines[1])
    )


def _table_flowable(lines: list[str], styles) -> Table:
    header = _split_table_cells(lines[0])
    ncol = len(header)
    data: list[list] = [
        [Paragraph(_inline_md_to_rl(c), styles["WclCellHeader"]) for c in header]
    ]
    for ln in lines[2:]:  # skip the separator row at index 1
        cells = _split_table_cells(ln)
        cells = (cells + [""] * ncol)[:ncol]  # normalize ragged rows to header width
        data.append([Paragraph(_inline_md_to_rl(c), styles["WclCell"]) for c in cells])
    table = Table(data, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4b2e1e")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b8a07e")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3ece0")]),
            ]
        )
    )
    return table


_BULLET_RE = re.compile(r"^\s*[-*]\s+")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+")


def _markdown_flowables(content: str, styles) -> list:
    """A pragmatic markdown → flowables conversion.

    Handles headings, GFM pipe tables, bulleted lists (incl. an intro line followed
    by bullets), numbered lists, and paragraphs; long tokens wrap via CJK word-wrap.
    """
    _ensure_pdf_styles(styles)
    flowables: list = []
    for block in re.split(r"\n\s*\n", content.strip()):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()

        # GFM pipe table.
        if _looks_like_table(lines):
            flowables.append(_table_flowable(lines, styles))
            flowables.append(Spacer(1, 8))
            continue

        # Pure bulleted list.
        if all(_BULLET_RE.match(ln) for ln in lines):
            for ln in lines:
                item = _BULLET_RE.sub("", ln)
                flowables.append(Paragraph(f"• {_inline_md_to_rl(item)}", styles["BodyText"]))
            flowables.append(Spacer(1, 6))
            continue

        # Pure numbered list (preserve the authored numbers).
        if all(_NUMBERED_RE.match(ln) for ln in lines):
            for ln in lines:
                num = re.match(r"^\s*(\d+)[.)]\s+", ln).group(1)
                item = _NUMBERED_RE.sub("", ln)
                flowables.append(Paragraph(f"{num}. {_inline_md_to_rl(item)}", styles["BodyText"]))
            flowables.append(Spacer(1, 6))
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", lines[0])
        if heading:
            level = min(len(heading.group(1)), 3)
            flowables.append(Paragraph(_inline_md_to_rl(heading.group(2)), styles[f"Heading{level}"]))
            rest = "\n".join(lines[1:]).strip()
            if rest:
                flowables.append(Paragraph(_inline_md_to_rl(rest.replace("\n", "<br/>")), styles["BodyText"]))
            continue

        # Intro line followed by a bullet or numbered list (common agent shape).
        if len(lines) >= 2 and not _BULLET_RE.match(lines[0]) and not _NUMBERED_RE.match(lines[0]):
            rest = lines[1:]
            if rest and all(_BULLET_RE.match(ln) or _NUMBERED_RE.match(ln) for ln in rest):
                flowables.append(Paragraph(_inline_md_to_rl(lines[0]), styles["BodyText"]))
                for ln in rest:
                    if _BULLET_RE.match(ln):
                        flowables.append(Paragraph(f"• {_inline_md_to_rl(_BULLET_RE.sub('', ln))}", styles["BodyText"]))
                    else:
                        num = re.match(r"^\s*(\d+)[.)]\s+", ln).group(1)
                        flowables.append(Paragraph(f"{num}. {_inline_md_to_rl(_NUMBERED_RE.sub('', ln))}", styles["BodyText"]))
                flowables.append(Spacer(1, 6))
                continue

        flowables.append(
            Paragraph(_inline_md_to_rl(block.replace("\n", "<br/>")), styles["BodyText"])
        )
        flowables.append(Spacer(1, 6))
    return flowables


def _series_from_graph(graph_json: dict) -> list[tuple[str, list, list]]:
    """Best-effort extraction of (name, xs, ys) series from a WCL graph payload."""
    series_out: list[tuple[str, list, list]] = []
    data = graph_json.get("data") if isinstance(graph_json, dict) else None
    series = (data or {}).get("series") if isinstance(data, dict) else None
    if not isinstance(series, list):
        return series_out
    for i, s in enumerate(series):
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or f"series {i + 1}")
        points = s.get("data")
        xs: list = []
        ys: list = []
        if isinstance(points, list):
            for j, pt in enumerate(points):
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    xs.append(pt[0])
                    ys.append(pt[1])
                elif isinstance(pt, dict) and "y" in pt:
                    xs.append(pt.get("x", j))
                    ys.append(pt["y"])
                elif isinstance(pt, (int, float)):
                    xs.append(j)
                    ys.append(pt)
        if xs and ys:
            series_out.append((name, xs, ys))
    return series_out


def _graph_image(graph: dict) -> Image | None:
    """Render one captured graph to a reportlab Image, or None if unplottable."""
    series = _series_from_graph(graph.get("graph_json") or {})
    if not series:
        return None
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    try:
        for name, xs, ys in series:
            ax.plot(xs, ys, label=name)
        title = graph.get("data_type", "Graph")
        if graph.get("report_code"):
            title += f" — {graph['report_code']}"
        ax.set_title(title)
        ax.legend(fontsize="x-small", loc="best")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130)
        buf.seek(0)
    finally:
        plt.close(fig)
    return Image(buf, width=6.5 * inch, height=3.2 * inch)


def render_report_pdf(
    *,
    title: str,
    generated_at: datetime,
    messages: list[dict[str, Any]],
    graphs: list[dict[str, Any]],
) -> bytes:
    """Render the conversation into PDF bytes (header + analysis + charts).

    ``messages``: dicts with ``role``/``content``/``status``.
    ``graphs``: dicts with ``data_type``/``report_code``/``graph_json``.
    A conversation with no captured graphs still produces an analysis-only PDF.
    """
    styles = getSampleStyleSheet()
    _ensure_pdf_styles(styles)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    story: list = [
        Paragraph(html.escape(title), styles["Title"]),
        Paragraph(
            f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]
        ),
        Spacer(1, 12),
    ]

    if any(m.get("role") == "agent" for m in messages):
        story.append(Paragraph("Analysis", styles["Heading1"]))
        # Render in conversation order so each answer sits under the question that
        # prompted it (US3): user turns become context headings, agent turns the body.
        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "user":
                if content.strip():
                    story.append(Paragraph(_inline_md_to_rl(content), styles["WclQuestion"]))
            elif role == "agent":
                story.extend(_markdown_flowables(content, styles))
                if m.get("status") == "partial":
                    story.append(Paragraph("<i>(interrupted — partial response)</i>", styles["Italic"]))
                story.append(Spacer(1, 10))
    else:
        story.append(Paragraph("No written analysis in this conversation.", styles["BodyText"]))

    rendered = [img for g in graphs if (img := _graph_image(g)) is not None]
    if rendered:
        story.append(PageBreak())
        story.append(Paragraph("Graphs", styles["Heading1"]))
        for img in rendered:
            story.append(img)
            story.append(Spacer(1, 12))

    doc.build(story)
    return buf.getvalue()
