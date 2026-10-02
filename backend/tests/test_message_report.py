"""Per-message PDF report (feature 005 / US5): scoped to one reply."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from backend.app.db import repository as repo
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.services.artifacts import capture_artifact_from_tool
from wcl_agent.tools import create_chart


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


async def _seed(session_factory):
    """Two turns; a chart captured on the first agent reply only."""
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash")
        await repo.add_message(s, conv.id, "user", "FIRST QUESTION about parses")
        a1 = await repo.add_message(s, conv.id, "agent", "FIRST ANSWER with a chart")
        spec = capture_artifact_from_tool(
            "create_chart", True, create_chart("line", "DPS", '[{"name":"R","y":[1,2,3]}]')
        )
        await repo.add_artifact(
            s, conversation_id=conv.id, kind=spec.kind, title=spec.title, spec_json=spec.model_dump()
        )
        await repo.assign_message_seq_to_turn_captures(s, conv.id, a1.seq)
        await repo.add_message(s, conv.id, "user", "SECOND QUESTION unrelated")
        a2 = await repo.add_message(s, conv.id, "agent", "SECOND ANSWER no chart")
        await repo.assign_message_seq_to_turn_captures(s, conv.id, a2.seq)
        await s.commit()
        return str(conv.id), str(a1.id), str(a2.id)


async def test_message_report_is_scoped_and_valid(session_factory):
    conv_id, a1_id, _a2_id = await _seed(session_factory)
    client = _client_with(session_factory)
    try:
        resp = await client.get(f"/api/conversations/{conv_id}/messages/{a1_id}/report.pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "wcl-message-" in resp.headers["content-disposition"]
        assert resp.content[:4] == b"%PDF"
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_message_report_404_for_unknown_message(session_factory):
    conv_id, _a1, _a2 = await _seed(session_factory)
    client = _client_with(session_factory)
    try:
        import uuid

        bogus = uuid.uuid4()
        resp = await client.get(f"/api/conversations/{conv_id}/messages/{bogus}/report.pdf")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_message_report_404_for_user_message(session_factory):
    # Only agent replies are exportable per-message; a user message id is a 404.
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash")
        u = await repo.add_message(s, conv.id, "user", "hi")
        await s.commit()
        conv_id, user_id = str(conv.id), str(u.id)

    client = _client_with(session_factory)
    try:
        resp = await client.get(f"/api/conversations/{conv_id}/messages/{user_id}/report.pdf")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await client.aclose()
