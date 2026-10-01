"""US5 tests: PDF export happy path, analysis-only, unknown id, and render failure."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.api import reports as reports_module
from backend.app.db import repository as repo
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.services.pdf_report import render_report_pdf

SAMPLE_GRAPH = {"data": {"series": [{"name": "Player", "data": [[0, 100], [1000, 250], [2000, 180]]}]}}


def _client_with(session_factory) -> AsyncClient:
    async def override_get_session():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


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


async def test_download_report_happy_path(session_factory):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="My Raid")
        await repo.add_message(s, conv.id, "user", "analyze this")
        await repo.add_message(s, conv.id, "agent", "## Analysis\n\nLooks good.")
        await repo.add_captured_graph(
            s, conversation_id=conv.id, report_code="ABCD", data_type="DamageDone", graph_json=SAMPLE_GRAPH
        )
        await s.commit()
        conv_id = conv.id

    client = _client_with(session_factory)
    try:
        resp = await client.get(f"/api/conversations/{conv_id}/report.pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content[:4] == b"%PDF"
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_download_report_no_graphs(session_factory):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Texty")
        await repo.add_message(s, conv.id, "agent", "Analysis without graphs.")
        await s.commit()
        conv_id = conv.id

    client = _client_with(session_factory)
    try:
        resp = await client.get(f"/api/conversations/{conv_id}/report.pdf")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_download_report_unknown_is_404(session_factory):
    client = _client_with(session_factory)
    try:
        resp = await client.get(f"/api/conversations/{uuid.uuid4()}/report.pdf")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_download_report_render_failure_is_500(session_factory, monkeypatch):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", title="Boom")
        await repo.add_message(s, conv.id, "agent", "text")
        await s.commit()
        conv_id = conv.id

    def boom(**kwargs):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(reports_module, "render_report_pdf", boom)

    client = _client_with(session_factory)
    try:
        resp = await client.get(f"/api/conversations/{conv_id}/report.pdf")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "pdf_generation_failed"
    finally:
        app.dependency_overrides.clear()
        await client.aclose()
