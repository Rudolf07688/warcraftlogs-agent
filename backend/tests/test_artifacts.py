"""Artifact capture + persistence + reload (feature 005 / US2)."""

from __future__ import annotations

from backend.app.db import repository as repo
from backend.app.services.artifacts import capture_artifact_from_tool
from wcl_agent.tools import create_chart


# --- capture service ----------------------------------------------------------


def test_capture_from_valid_create_chart():
    result = create_chart("bar", "Specs", '[{"name":"Enh","y":[95,96]}]')
    spec = capture_artifact_from_tool("create_chart", True, result)
    assert spec is not None
    assert spec.kind == "bar"
    assert spec.title == "Specs"


def test_capture_ignores_other_tools_and_failures():
    result = create_chart("bar", "Specs", '[{"name":"Enh","y":[95]}]')
    assert capture_artifact_from_tool("get_report_table", True, result) is None
    assert capture_artifact_from_tool("create_chart", False, result) is None
    assert capture_artifact_from_tool("create_chart", True, {"status": "error"}) is None


# --- persistence + linkage + reload endpoint ----------------------------------


async def test_persisted_artifact_returned_with_figure_and_seq(as_user, session_factory):
    tid = as_user.tenant_id
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash", tenant_id=tid)
        await repo.add_message(s, conv.id, "user", "plot it", tenant_id=tid)
        agent_msg = await repo.add_message(s, conv.id, "agent", "here you go", tenant_id=tid)
        spec = capture_artifact_from_tool(
            "create_chart", True, create_chart("line", "DPS", '[{"name":"R","y":[1,2,3]}]')
        )
        await repo.add_artifact(
            s, tenant_id=tid, conversation_id=conv.id, kind=spec.kind, title=spec.title,
            spec_json=spec.model_dump(),
        )
        await repo.assign_message_seq_to_turn_captures(s, conv.id, agent_msg.seq, tenant_id=tid)
        await s.commit()
        conv_id = str(conv.id)
        seq = agent_msg.seq

    resp = await as_user.client.get(f"/api/conversations/{conv_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["artifacts"]) == 1
    art = body["artifacts"][0]
    assert art["message_seq"] == seq
    assert art["kind"] == "line"
    assert art["figure"]["data"] and art["figure"]["layout"]


async def test_assign_seq_only_touches_unlinked_captures(session, tenant_id):
    conv = await repo.create_conversation(session, model="gemini-3.6-flash", tenant_id=tenant_id)
    spec = capture_artifact_from_tool(
        "create_chart", True, create_chart("line", "A", '[{"name":"R","y":[1]}]')
    )
    a = await repo.add_artifact(
        session, tenant_id=tenant_id, conversation_id=conv.id, kind=spec.kind,
        title=spec.title, spec_json=spec.model_dump()
    )
    await repo.assign_message_seq_to_turn_captures(session, conv.id, 1, tenant_id=tenant_id)
    b = await repo.add_artifact(
        session, tenant_id=tenant_id, conversation_id=conv.id, kind=spec.kind,
        title=spec.title, spec_json=spec.model_dump()
    )
    await session.commit()
    arts = await repo.list_artifacts(session, conv.id, tenant_id=tenant_id)
    by_id = {x.id: x for x in arts}
    assert by_id[a.id].message_seq == 1
    assert by_id[b.id].message_seq is None
