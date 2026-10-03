"""Per-message PDF report (feature 005 / US5): scoped to one reply (tenant-scoped US3)."""

from __future__ import annotations

import uuid

from backend.app.db import repository as repo
from backend.app.services.artifacts import capture_artifact_from_tool
from wcl_agent.tools import create_chart


async def _seed(session_factory, tid):
    """Two turns; a chart captured on the first agent reply only."""
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", tenant_id=tid)
        await repo.add_message(s, conv.id, "user", "FIRST QUESTION about parses", tenant_id=tid)
        a1 = await repo.add_message(s, conv.id, "agent", "FIRST ANSWER with a chart", tenant_id=tid)
        spec = capture_artifact_from_tool(
            "create_chart", True, create_chart("line", "DPS", '[{"name":"R","y":[1,2,3]}]')
        )
        await repo.add_artifact(
            s, tenant_id=tid, conversation_id=conv.id, kind=spec.kind, title=spec.title,
            spec_json=spec.model_dump()
        )
        await repo.assign_message_seq_to_turn_captures(s, conv.id, a1.seq, tenant_id=tid)
        await repo.add_message(s, conv.id, "user", "SECOND QUESTION unrelated", tenant_id=tid)
        a2 = await repo.add_message(s, conv.id, "agent", "SECOND ANSWER no chart", tenant_id=tid)
        await repo.assign_message_seq_to_turn_captures(s, conv.id, a2.seq, tenant_id=tid)
        await s.commit()
        return str(conv.id), str(a1.id), str(a2.id)


async def test_message_report_is_scoped_and_valid(as_user, session_factory):
    conv_id, a1_id, _a2_id = await _seed(session_factory, as_user.tenant_id)
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/messages/{a1_id}/report.pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "wcl-message-" in resp.headers["content-disposition"]
    assert resp.content[:4] == b"%PDF"


async def test_message_report_404_for_unknown_message(as_user, session_factory):
    conv_id, _a1, _a2 = await _seed(session_factory, as_user.tenant_id)
    bogus = uuid.uuid4()
    resp = await as_user.client.get(f"/api/conversations/{conv_id}/messages/{bogus}/report.pdf")
    assert resp.status_code == 404


async def test_message_report_404_for_user_message(as_user, session_factory):
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", tenant_id=tid)
        u = await repo.add_message(s, conv.id, "user", "hi", tenant_id=tid)
        await s.commit()
        conv_id, user_id = str(conv.id), str(u.id)

    resp = await as_user.client.get(f"/api/conversations/{conv_id}/messages/{user_id}/report.pdf")
    assert resp.status_code == 404
