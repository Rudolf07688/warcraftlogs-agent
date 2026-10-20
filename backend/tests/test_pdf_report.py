"""PDF rendering (feature 017): findings Markdown → sanitised HTML → WeasyPrint PDF."""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import pytest
from pypdf import PdfReader

from backend.app.services.charts import graph_to_svg
from backend.app.services.pdf_report import (
    ReportDocument,
    ReportFigure,
    findings_to_html,
    render_report_pdf,
)

_RICH = (
    "# Pull Analysis\n\n"
    "Intro paragraph with a very long unbroken token "
    "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789aBcDeFgHiJkLmNoPqRsTuVwXyZ.\n\n"
    "| Boss | DPS | Parse |\n"
    "|------|-----|-------|\n"
    "| Ulgrax the Devourer | 1,234,567 | 95 |\n"
    "| Sikran | 2,345,678 | 88 |\n\n"
    "Here is what to fix:\n"
    "- keep your uptime high\n"
    "- stop dying to the swirl\n\n"
    "1. precast before the pull\n"
    "2. save cooldowns for burn\n\n"
    "Some **bold**, some *italic*, and `inline_code`.\n"
)

_GRAPH = {
    "data_type": "DamageDone",
    "report_code": "aBcDeFgH",
    "graph_json": {"data": {"series": [{"name": "DPS", "data": [[0, 100], [1, 200], [2, 150]]}]}},
}


def _doc(body: str, **kw) -> ReportDocument:
    kw.setdefault("title", "WCL Report")
    kw.setdefault("scope", "conversation")
    return ReportDocument(generated_at=datetime(2026, 10, 19, 14, 2, tzinfo=timezone.utc), body_markdown=body, **kw)


def _pages(pdf: bytes) -> list[str]:
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]


def test_render_report_pdf_handles_rich_markdown_and_graph():
    fig = ReportFigure(title="DamageDone — aBcDeFgH", svg=graph_to_svg(_GRAPH["graph_json"]))
    pdf = render_report_pdf(_doc(_RICH, figures=(fig,)))
    assert pdf[:4] == b"%PDF"
    text = "\n".join(_pages(pdf))
    assert "Ulgrax the Devourer" in text
    assert "**" not in text and "|---" not in text


def test_render_report_pdf_analysis_only_without_graphs():
    pdf = render_report_pdf(_doc("Short note."))
    assert pdf[:4] == b"%PDF"
    assert "Short note." in "\n".join(_pages(pdf))


# --- US1: clean, readable report text ----------------------------------------------

_FIXTURES = sorted((Path(__file__).parent / "fixtures" / "findings").glob("*.md"))
# Formatting syntax or markup that must never survive into the PDF text (FR-001).
_MARKERS = ("**", "__", "##", "|---", "$$", "](", "<br", "<b>", "<script", "&lt;", "&gt;", "\\text", "\\frac")
_MD_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\((\S+?)\)")


def _uris(pdf: bytes) -> set[str]:
    out = set()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        for annot in page.get("/Annots") or []:
            action = annot.get_object().get("/A")
            if action and "/URI" in action:
                out.add(unquote(str(action["/URI"])))
    return out


def test_corpus_has_at_least_twenty_documents():
    assert len(_FIXTURES) >= 20  # SC-001


@pytest.mark.parametrize("path", _FIXTURES, ids=lambda p: p.stem)
def test_corpus_document_renders_without_visible_markup(path):
    source = path.read_text()
    pdf = render_report_pdf(_doc(source))
    assert pdf[:4] == b"%PDF"
    text = "\n".join(_pages(pdf))
    for marker in _MARKERS:
        assert marker not in text, f"{marker!r} visible in {path.name}"
    # Every Markdown link is a clickable annotation (SC-003), except unsafe schemes.
    uris = _uris(pdf)
    for _label, url in _MD_LINK.findall(source):
        if url.startswith(("http", "mailto")):
            assert unquote(url) in uris, f"{url} not clickable in {path.name}"


def test_non_latin_names_and_emoji_are_kept():
    pdf = render_report_pdf(_doc((_FIXTURES[0].parent / "names.md").read_text()))
    text = "\n".join(_pages(pdf))
    for name in ("Ælfwyn", "Kâzzak", "Иванушка", "김철수", "王小明"):
        assert name in text


def test_nested_lists_keep_depth_and_authored_numbering():
    out = findings_to_html("- a\n  - b\n    - c\n\n3. three\n4. four\n")
    assert out.count("<ul>") == 3
    assert '<ol start="3" style="counter-reset: list-item 2">' in out


def test_task_list_renders_checkboxes():
    out = findings_to_html("- [x] done\n- [ ] open\n")
    assert out.count("☑") == 1 and out.count("☐") == 1
    assert "[x]" not in out and "[ ]" not in out and "<input" not in out


def test_table_alignment_is_kept_and_ragged_rows_fixed():
    out = findings_to_html("| a | b |\n|:--|--:|\n| 1 | 2 | 3 |\n| only |\n")
    assert "text-align:left" in out.replace(" ", "") and "text-align:right" in out.replace(" ", "")
    assert "<td>3</td>" not in out  # extra cell trimmed
    assert out.count("<tr>") == 3  # header + 2 body rows, short row padded


def test_currency_is_not_maths():
    out = findings_to_html("Repairs cost $5 and flasks $10.")
    assert "$5" in out and "$10" in out and "<img" not in out


def test_inline_and_block_maths_are_typeset():
    out = findings_to_html("Uptime $a^2$ here.\n\n$$\\frac{d}{t}$$\n")
    assert 'class="math-inline"' in out and 'class="math-block"' in out
    assert "data:image/svg+xml;base64," in out


def test_untypesettable_maths_falls_back_to_plain_text():
    out = findings_to_html("$$\\badcommand{x} + \\text{Combustion}$$")
    assert "<em>" in out and "Combustion" in out
    plain = re.sub(r"<[^>]+>", "", out)
    assert "\\" not in plain and "{" not in plain and "$" not in plain


def test_raw_html_is_sanitised():
    out = findings_to_html(
        'a<br>b <b>bold</b> <script>alert("x")</script> <!-- c --> '
        '<iframe src="https://evil.example/"></iframe> <a href="javascript:alert(1)">bad</a>'
    )
    assert "<br" in out and "<b>bold</b>" in out
    assert "script" not in out and "alert" not in out and "iframe" not in out
    assert "<!--" not in out and "javascript:" not in out


def test_remote_images_become_text():
    out = findings_to_html("![Boss portrait](https://evil.example/boss.png) ![](https://evil.example/t.gif)")
    assert "<img" not in out
    assert "Boss portrait" in out and "https://evil.example/t.gif" in out


def test_rendering_never_fetches_files_or_network(monkeypatch, tmp_path):
    import socket

    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT")

    def no_connect(*_a, **_k):
        raise AssertionError("network access during PDF render")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    body = (
        f'<img src="file://{secret}"> <img src="http://127.0.0.1:9/x.png">\n\n'
        '<span style="background:url(http://127.0.0.1:9/y)">styled</span>\n\n'
        f"![local](file://{secret})"
    )
    pdf = render_report_pdf(_doc(body))
    assert pdf[:4] == b"%PDF"
    assert "TOP-SECRET-CONTENT" not in "\n".join(_pages(pdf))


# --- US2: a report that looks like a real document ------------------------------


def _long_table(rows: int = 90) -> str:
    head = "| Player | Spec | Parse | Damage taken | Notes |\n|---|---|---|---|---|\n"
    body = "".join(f"| Player{i} | Fire Mage | {i % 100} | {i * 1000:,} | Stood in fire on pull {i} |\n" for i in range(rows))
    return "## Results by Player\n\n" + head + body


def test_title_block_shows_scope_and_utc_time():
    first = _pages(render_report_pdf(_doc("Body.", title="Fyrakk Heroic")))[0]
    assert "Fyrakk Heroic" in first and "Whole conversation" in first
    assert "2026-10-19 14:02 UTC" in first


def test_single_answer_title_block_shows_question():
    first = _pages(render_report_pdf(_doc("Body.", scope="message", question="Why did we wipe on Fyrakk?")))[0]
    assert "Single answer" in first and "Why did we wipe on Fyrakk?" in first


def test_partial_answer_is_marked():
    text = _pages(render_report_pdf(_doc("Body.", scope="message", partial=True)))[0]
    assert "partial answer" in text
    assert "partial answer" not in _pages(render_report_pdf(_doc("Body.")))[0]


def test_page_numbers_running_header_and_repeated_table_header():
    pages = _pages(render_report_pdf(_doc(_long_table(), title="Unique Raid Title")))
    assert len(pages) >= 3
    assert f"Page 1 of {len(pages)}" in pages[0]
    assert pages[0].count("Unique Raid Title") == 1  # title block only, no running header
    assert all("Unique Raid Title" in p for p in pages[1:])  # running header from page 2
    assert all("Damage taken" in p for p in pages)  # thead repeats after every break


def test_interpolated_text_is_escaped():
    text = _pages(render_report_pdf(_doc("Body.", title="<b>Raid & Co</b>", scope="message", question="<i>why</i>?")))[0]
    assert "<b>Raid & Co</b>" in text and "<i>why</i>?" in text


def test_long_tokens_get_break_points_but_links_and_numbers_do_not():
    url = "https://www.warcraftlogs.com/reports/AbC123xYz#fight=12&type=damage-done&source=7"
    out = findings_to_html(f"[{url}]({url}) and 1,234,567 and AT&T_{'x' * 40}")
    assert f'href="{url.replace("&", "&amp;")}"' in out  # target untouched
    assert "\u200b" in out  # visible long text can wrap
    assert "1,234,567" in out  # ordinary numbers never split
    assert "&amp;\u200b" in out and "&\u200bamp;" not in out  # entities stay whole


# --- US3: charts that belong in the report -------------------------------------------


def _fig(title: str, **kw) -> ReportFigure:
    kw.setdefault("svg", graph_to_svg(_GRAPH["graph_json"]))
    return ReportFigure(title=title, **kw)


def test_charts_section_numbers_and_orders_figures_after_findings():
    figs = (_fig("DamageDone — aBcDeFgH"), _fig("Raid DPS"))
    pages = _pages(render_report_pdf(_doc("Short findings.", figures=figs)))
    first_chart_page = next(i for i, p in enumerate(pages) if "Figure 1 — DamageDone — aBcDeFgH" in p)
    assert first_chart_page > 0  # Charts start on a new page
    text = "\n".join(pages)
    assert text.index("Figure 1 — ") < text.index("Figure 2 — Raid DPS")


def test_figure_source_link_is_clickable():
    url = "https://www.warcraftlogs.com/reports/aBcDeFgH#fight=3"
    pdf = render_report_pdf(_doc("x", figures=(_fig("DPS", source_url=url),)))
    assert url in _uris(pdf)


def test_undrawable_chart_shows_note_and_report_still_renders():
    pdf = render_report_pdf(_doc("x", figures=(_fig("Broken", svg=None),)))
    assert pdf[:4] == b"%PDF"
    text = "\n".join(_pages(pdf))
    assert "Chart unavailable" in text and "Figure 1 — Broken" in text


def test_no_charts_section_without_figures():
    assert "Charts" not in "\n".join(_pages(render_report_pdf(_doc("Findings only."))))


# --- QA follow-ups (2026-10-19 sweep) ------------------------------------------------


def test_model_supplied_data_images_become_text():
    # SEC-001: only the renderer's own images may reach WeasyPrint.
    svg = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4="
    out = findings_to_html(
        f'<img src="data:image/svg+xml;base64,{svg}" alt="boss icon"> '
        f'![bomb](data:image/png;base64,{svg}) <a href="data:text/html,hi">data link</a>'
    )
    assert "<img" not in out and "data:" not in out
    assert "boss icon" in out and "data link" in out


def test_forged_maths_placeholders_are_inert():
    out = findings_to_html("Before 0 after, and $a^2$.")
    assert out.count("<img") == 1  # only the real equation
    assert "" not in out and "" not in out


def _table_overflow(markdown: str) -> float:
    """How far (px) the widest table sticks out past the page content box."""
    from weasyprint import CSS, HTML

    from backend.app.services import pdf_report as pr

    doc = HTML(string=pr._document_html(_doc(markdown)), base_url=None, url_fetcher=pr._FETCHER).render(
        stylesheets=[CSS(string=pr.REPORT_CSS)]
    )
    worst = float("-inf")
    for page in doc.pages:
        box = page._page_box
        right = box.content_box_x() + box.width

        def walk(b):
            yield b
            for c in getattr(b, "children", None) or []:
                yield from walk(c)

        for b in walk(box):
            if type(b).__name__ == "TableBox":
                worst = max(worst, b.position_x + b.margin_width() - right)
    return worst


_TEN_COLS = (
    "| Player | Spec | Role | Parse | DPS | Deaths | Interrupts | Dispels | Damage taken | Report |\n"
    + "|---" * 10 + "|\n"
    + "".join(
        f"| Ælfwyn-Silvermoon{i} | Frost Mage | Ranged | 9{i} | 1,234,56{i} | {i} | 1{i} | {i} | 4,567,890 | "
        f"AbC123xYzQwErTy{i} |\n"
        for i in range(6)
    )
)
_SEVEN_CODES = "| " + " | ".join(f"Col{i}" for i in range(7)) + " |\n" + "|---" * 7 + "|\n" + (
    "| " + " | ".join("Q7xKp2mVbR9tLwZ3aYcN" for _ in range(7)) + " |\n"
)


@pytest.mark.parametrize("markdown", [_TEN_COLS, _SEVEN_CODES], ids=["ten-columns", "seven-codes"])
def test_wide_tables_fit_inside_the_margins(markdown):
    assert _table_overflow(markdown) <= 0.5  # FR-011


def test_wide_table_fixture_fits_and_numbers_stay_whole():
    source = (_FIXTURES[0].parent / "wide-table.md").read_text()
    assert _table_overflow(source) <= 0.5
    out = findings_to_html(_TEN_COLS)
    assert "1,234,565" in out and "4,567,890" in out  # numbers never split


def test_very_long_body_is_shortened_with_a_note():
    body = ("A paragraph of findings. " * 40 + "\n\n") * 80  # ~80 k characters
    text = "\n".join(_pages(render_report_pdf(_doc(body))))
    assert "Report shortened" in text


def test_huge_table_is_capped():
    rows = "".join(f"| P{i} | {i} |\n" for i in range(500))
    out = findings_to_html("| Player | Parse |\n|---|---|\n" + rows)
    assert out.count("<tr>") <= 202  # header + 200 rows + the "not shown" row
    assert "300 more rows not shown" in out


def test_maths_caps_fall_back_to_text():
    long_eq = "$$" + "+".join("x" for _ in range(200)) + "$$"
    assert "<img" not in findings_to_html(long_eq)
    many = " ".join(f"${chr(97 + i % 26)}^2$" for i in range(61))
    assert findings_to_html(many).count("<img") == 60


def test_caption_links_only_http():
    # SEC-005: a model-supplied source_url only becomes a link when it is http(s).
    figs = tuple(
        _fig(f"F{n}", source_url=url)
        for n, url in enumerate(("javascript:alert(1)", "file:///etc/passwd", "reports/x", "https://ok.example/r"))
    )
    uris = _uris(render_report_pdf(_doc("x", figures=figs)))
    assert uris == {"https://ok.example/r"}


def test_omitted_charts_are_noted():
    text = "\n".join(_pages(render_report_pdf(_doc("x", figures=(_fig("A"),), figures_omitted=3))))
    assert "3 more charts not shown" in text
