"""US5 tests: PDF export happy path, analysis-only, unknown id, and render failure."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.app.api import reports as reports_module
from backend.app.db import repository as repo
from backend.app.services.pdf_report import render_report_pdf

SAMPLE_GRAPH = {"data": {"series": [{"name": "Player", "data": [[0, 100], [1000, 250], [2000, 180]]}]}}


def test_render_pdf_returns_pdf_bytes():
    pdf = render_report_pdf(
        title="Test Raid",
        generated_at=datetime.now(timezone.utc),
        messages=[{"role": "agent", "content": "# Findings\n\n- point one\n- point two", "status": "complete"}],
        graphs=[{"data_type": "DamageDone", "report_code": "ABCD", "graph_json": SAMPLE_GRAPH}],
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_render_pdf_analysis_only():
    pdf = render_report_pdf(
        title="No Graphs",
        generated_at=datetime.now(timezone.utc),
        messages=[{"role": "agent", "content": "Just text analysis.", "status": "complete"}],
        graphs=[],
    )
    assert pdf[:4] == b"%PDF"


async def test_download_report_happy_path(as_user, session_factory):
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


async def test_download_report_no_graphs(as_user, session_factory):
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Texty", tenant_id=tid)
        await repo.add_message(s, conv.id, "agent", "Analysis without graphs.", tenant_id=tid)
        await s.commit()
        conv_id = conv.id

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/report.pdf")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


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
