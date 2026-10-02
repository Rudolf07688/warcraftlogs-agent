"""US3: PDF rendering handles rich markdown (tables, lists, long tokens, graphs)."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.services.pdf_report import render_report_pdf

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


def test_render_report_pdf_handles_rich_markdown_and_graph():
    messages = [
        {"role": "user", "content": "Why did we wipe on Ulgrax?", "status": "complete"},
        {"role": "agent", "content": _RICH, "status": "complete"},
    ]
    pdf = render_report_pdf(
        title="WCL Report",
        generated_at=datetime.now(timezone.utc),
        messages=messages,
        graphs=[_GRAPH],
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_render_report_pdf_analysis_only_without_graphs():
    messages = [{"role": "agent", "content": "Short note.", "status": "complete"}]
    pdf = render_report_pdf(
        title="WCL Report",
        generated_at=datetime.now(timezone.utc),
        messages=messages,
        graphs=[],
    )
    assert pdf[:4] == b"%PDF"
