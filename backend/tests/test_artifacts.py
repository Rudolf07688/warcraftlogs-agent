"""Artifact capture + persistence + reload (feature 005 / US2)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from backend.app.db import repository as repo
from backend.app.db.session import get_session
from backend.app.main import app
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


async def test_persisted_artifact_returned_with_figure_and_seq(session_factory):
    # Seed a conversation with a user + agent message and an artifact, then link it.
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash")
        await repo.add_message(s, conv.id, "user", "plot it")
        agent_msg = await repo.add_message(s, conv.id, "agent", "here you go")
        spec = capture_artifact_from_tool(
            "create_chart", True, create_chart("line", "DPS", '[{"name":"R","y":[1,2,3]}]')
        )
        await repo.add_artifact(
            s,
            conversation_id=conv.id,
            kind=spec.kind,
            title=spec.title,
            spec_json=spec.model_dump(),
        )
        await repo.assign_message_seq_to_turn_captures(s, conv.id, agent_msg.seq)
        await s.commit()
        conv_id = str(conv.id)
        seq = agent_msg.seq

    client = _client_with(session_factory)
    try:
        resp = await client.get(f"/api/conversations/{conv_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["artifacts"]) == 1
        art = body["artifacts"][0]
        assert art["message_seq"] == seq
        assert art["kind"] == "line"
        # The figure is rebuilt from the stored spec on read.
        assert art["figure"]["data"] and art["figure"]["layout"]
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_assign_seq_only_touches_unlinked_captures(session_factory):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model="gemini-3.6-flash")
        spec = capture_artifact_from_tool(
            "create_chart", True, create_chart("line", "A", '[{"name":"R","y":[1]}]')
        )
        a = await repo.add_artifact(
            s, conversation_id=conv.id, kind=spec.kind, title=spec.title, spec_json=spec.model_dump()
        )
        await repo.assign_message_seq_to_turn_captures(s, conv.id, 1)
        # A later artifact from a new turn is unlinked until its own turn end.
        b = await repo.add_artifact(
            s, conversation_id=conv.id, kind=spec.kind, title=spec.title, spec_json=spec.model_dump()
        )
        await s.commit()
        arts = await repo.list_artifacts(s, conv.id)
        by_id = {x.id: x for x in arts}
        assert by_id[a.id].message_seq == 1
        assert by_id[b.id].message_seq is None
