"""US5 tests: PDF export happy path, analysis-only, unknown id, and render failure."""

from __future__ import annotations

import io
import threading
import time
import uuid
from datetime import datetime, timezone

import pytest
from pypdf import PdfReader

from backend.app.api import reports as reports_module
from backend.app.db import repository as repo
from backend.app.services import report_synthesis
from backend.app.services.charts import graph_to_svg
from backend.app.services.pdf_report import ReportDocument, ReportFigure, render_report_pdf

SAMPLE_GRAPH = {"data": {"series": [{"name": "Player", "data": [[0, 100], [1000, 250], [2000, 180]]}]}}

_FAKE_FINDINGS = "## Summary\n\nInvestigated boss parses.\n\n## Key Findings\n\n- 95th percentile"


def _mock_synthesis(monkeypatch, *, returns=_FAKE_FINDINGS, raises=None):
    """Patch the findings synthesis so endpoint tests don't call a live model."""
    async def fake(messages, *, scope, question=None):
        if raises is not None:
            raise raises
        return returns

    monkeypatch.setattr(reports_module.report_synthesis, "synthesize_findings", fake)


def test_render_pdf_returns_pdf_bytes():
    pdf = render_report_pdf(
        ReportDocument(
            title="Test Raid",
            scope="conversation",
            generated_at=datetime.now(timezone.utc),
            body_markdown="# Findings\n\n- point one\n- point two",
            figures=(ReportFigure(title="DamageDone — ABCD", svg=graph_to_svg(SAMPLE_GRAPH)),),
        )
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_render_pdf_analysis_only():
    pdf = render_report_pdf(
        ReportDocument(
            title="No Graphs",
            scope="conversation",
            generated_at=datetime.now(timezone.utc),
            body_markdown="Just text analysis.",
        )
    )
    assert pdf[:4] == b"%PDF"


async def test_download_report_happy_path(as_user, session_factory, monkeypatch):
    _mock_synthesis(monkeypatch)
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="My Raid", tenant_id=tid)
        await repo.add_message(s, conv.id, "user", "analyze this", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "## Analysis\n\nLooks good.", tenant_id=tid)
        await repo.add_captured_graph(
            s, tenant_id=tid, conversation_id=conv.id, report_code="ABCD",
            data_type="DamageDone", graph_json=SAMPLE_GRAPH
        )
        await s.commit()
        conv_id = conv.id

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:4] == b"%PDF"


async def test_download_report_no_graphs(as_user, session_factory, monkeypatch):
    _mock_synthesis(monkeypatch)
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Texty", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "Analysis without graphs.", tenant_id=tid)
        await s.commit()
        conv_id = conv.id

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


async def test_download_report_synthesizes_findings_not_transcript(as_user, session_factory, monkeypatch):
    # US2: the synthesis gets the full conversation slice; its output becomes the body.
    captured = {}

    async def fake(messages, *, scope, question=None):
        captured["scope"] = scope
        captured["contents"] = " ".join(m.get("content", "") for m in messages)
        return _FAKE_FINDINGS

    monkeypatch.setattr(reports_module.report_synthesis, "synthesize_findings", fake)
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Raid", tenant_id=tid)
        await repo.add_message(s, conv.id, "user", "how did we do on Ulgrax", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "Ulgrax parse was 95.", tenant_id=tid)
        await s.commit()
        conv_id = conv.id

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    assert captured["scope"] == "conversation"
    assert "Ulgrax parse was 95" in captured["contents"]  # full slice fed to synthesis


async def test_download_report_synthesis_failure_is_500(as_user, session_factory, monkeypatch):
    # US2/FR-018: a synthesis error fails closed with no partial file.
    _mock_synthesis(monkeypatch, raises=RuntimeError("model boom"))
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Boom", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "text", tenant_id=tid)
        await s.commit()
        conv_id = conv.id

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "pdf_generation_failed"


async def test_download_report_empty_synthesis_is_500(as_user, session_factory, monkeypatch):
    # US2/FR-018: empty model output is a malfunction, not a valid file.
    _mock_synthesis(monkeypatch, returns="   ")
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Empty", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "text", tenant_id=tid)
        await s.commit()
        conv_id = conv.id

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 500


async def test_download_report_unknown_is_404(as_user):
    resp = await as_user.client.get(f"/api/conversations/{uuid.uuid4()}/report.pdf")
    assert resp.status_code == 404


async def test_download_report_foreign_tenant_is_404(as_user, make_authed_client, session_factory):
    # A conversation owned by another tenant must be invisible (US3 isolation).
    other = await make_authed_client("other@example.com")
    try:
        async with session_factory() as s:
            conv = await repo.create_conversation(
                s, model="gemini-3.6-flash", title="Theirs", tenant_id=other.tenant_id
            )
            await s.commit()
            foreign_id = conv.id
        resp = await as_user.client.get(f"/api/conversations/{foreign_id}/report.pdf")
        assert resp.status_code == 404
    finally:
        await other.client.aclose()


async def test_download_report_render_failure_is_500(as_user, session_factory, monkeypatch):
    _mock_synthesis(monkeypatch)  # synthesis succeeds; the render step is what fails
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Boom", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "text", tenant_id=tid)
        await s.commit()
        conv_id = conv.id

    def boom(**kwargs):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(reports_module, "render_report_pdf", boom)

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "pdf_generation_failed"


# --- QA follow-ups (2026-10-19 sweep) ------------------------------------------------


async def _conv_with_chart(session_factory, tid, spec_json):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Charts", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "Analysis.", tenant_id=tid)
        await repo.add_artifact(
            s, tenant_id=tid, conversation_id=conv.id, kind="line", title="DPS", spec_json=spec_json
        )
        await s.commit()
        return conv.id


_SPEC = {"kind": "line", "title": "DPS", "series": [{"name": "Raid", "y": [1, 2, 3]}]}


async def test_charts_are_drawn_off_the_event_loop(as_user, session_factory, monkeypatch):
    # FR-022 (QA BUG-001/PERF-001): matplotlib must never run on the event loop thread.
    _mock_synthesis(monkeypatch)
    threads = []
    real = reports_module.charts.chart_spec_to_svg

    def spy(spec):
        threads.append(threading.current_thread() is threading.main_thread())
        return real(spec)

    monkeypatch.setattr(reports_module.charts, "chart_spec_to_svg", spy)
    conv_id = await _conv_with_chart(session_factory, as_user.tenant_id, _SPEC)
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    assert threads == [False]


async def test_malformed_chart_spec_prints_unavailable(as_user, session_factory, monkeypatch):
    _mock_synthesis(monkeypatch)
    conv_id = await _conv_with_chart(session_factory, as_user.tenant_id, ["not", "a", "dict"])
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(resp.content)).pages)
    assert "Chart unavailable" in text


async def test_render_timeout_fails_closed(as_user, session_factory, monkeypatch):
    _mock_synthesis(monkeypatch)
    monkeypatch.setattr(reports_module, "_RENDER_TIMEOUT_S", 0.2)
    monkeypatch.setattr(reports_module, "render_report_pdf", lambda doc: time.sleep(1) or b"%PDF-late")
    conv_id = await _conv_with_chart(session_factory, as_user.tenant_id, _SPEC)
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "pdf_generation_failed"


async def _conv_with_charts(session_factory, tid, n):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Charts", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "Analysis.", tenant_id=tid)
        for i in range(n):
            await repo.add_artifact(
                s, tenant_id=tid, conversation_id=conv.id, kind="line", title=f"C{i}",
                spec_json={**_SPEC, "title": f"Chart {i}"},
            )
        await s.commit()
        return conv.id


async def test_chart_and_pdf_work_run_on_the_dedicated_render_thread(as_user, session_factory, monkeypatch):
    # PERF-010: CPU-bound report work must not park threads of the shared default executor.
    _mock_synthesis(monkeypatch)
    names = []
    real_chart, real_render = reports_module.charts.chart_spec_to_svg, reports_module.render_report_pdf

    def spy_chart(spec):
        names.append(threading.current_thread().name)
        return real_chart(spec)

    def spy_render(doc):
        names.append(threading.current_thread().name)
        return real_render(doc)

    monkeypatch.setattr(reports_module.charts, "chart_spec_to_svg", spy_chart)
    monkeypatch.setattr(reports_module, "render_report_pdf", spy_render)
    conv_id = await _conv_with_chart(session_factory, as_user.tenant_id, _SPEC)
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    assert len(names) == 2 and all(n.startswith("pdf-render") for n in names)


async def test_no_figures_skips_the_render_thread(monkeypatch):
    # PERF-011: a report without charts doesn't queue for the render thread.
    class Refuse:
        def submit(self, *a, **kw):
            raise AssertionError("render pool used")

    monkeypatch.setattr(reports_module, "_RENDER_POOL", Refuse())
    assert await reports_module._figures((), ()) == ()


async def test_figures_are_capped_with_a_note(as_user, session_factory, monkeypatch):
    # PERF-012: one report can't hold the render thread for an unbounded number of charts.
    _mock_synthesis(monkeypatch)
    monkeypatch.setattr(reports_module, "_MAX_FIGURES", 2)
    conv_id = await _conv_with_charts(session_factory, as_user.tenant_id, 5)
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(resp.content)).pages)
    assert "Figure 2 — Chart 1" in text and "Figure 3" not in text
    assert "3 more charts not shown" in text


async def test_chart_step_timeout_prints_unavailable(as_user, session_factory, monkeypatch):
    # PERF-012: a chart that misses the chart-step deadline doesn't fail the report.
    _mock_synthesis(monkeypatch)
    monkeypatch.setattr(reports_module, "_CHARTS_TIMEOUT_S", 0.2)
    monkeypatch.setattr(reports_module.charts, "chart_spec_to_svg", lambda spec: time.sleep(0.6) or b"<svg/>")
    conv_id = await _conv_with_charts(session_factory, as_user.tenant_id, 2)
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(resp.content)).pages)
    assert text.count("Chart unavailable") == 2
