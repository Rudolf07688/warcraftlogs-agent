"""sc-213: a chart made in a chat comes back when the chat is reopened.

Drives ``_handle_turn`` with a fake socket and a scripted stream (like test_proposal_ws.py)
over the SQLite test DB: the real ``create_chart`` result is captured as the turn runs, then
``GET /api/conversations/{id}`` must return it under the agent message with a Plotly figure.
"""

from __future__ import annotations

import uuid

from backend.app.db import repository as repo
from backend.tests.test_proposal_ws import _FakeSocket, _quiet, _run, _tool_end
from wcl_agent.tools.tools import create_chart


def _stream(records):
    async def stream(*args, **kwargs):
        for r in records:
            yield r

    return stream


async def test_chart_is_returned_under_its_agent_message_on_reopen(as_user, patched_db, monkeypatch):
    result = await create_chart("bar", "Deaths", '[{"name":"Raid","x":["A","B"],"y":[3,5]}]')
    _quiet(
        monkeypatch,
        _stream([_tool_end("create_chart", result), {"type": "token", "text": "Here is the chart."}]),
    )
    sock = _FakeSocket()
    conv_id = await _run(sock, as_user, "plot deaths")

    live = next(f for f in sock.frames if f["type"] == "artifact")
    detail = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()
    async with patched_db() as db:
        agent = [m for m in await repo.list_messages(db, conv_id, tenant_id=as_user.tenant_id) if m.role == "agent"]
    assert [(a["id"], a["message_seq"]) for a in detail["artifacts"]] == [
        (live["artifact_id"], agent[0].seq)
    ]
    assert detail["artifacts"][0]["figure"] == live["figure"]  # same figure live and on reopen
    assert [m["seq"] for m in detail["messages"] if m["role"] == "agent"] == [agent[0].seq]


async def test_a_second_turn_does_not_steal_the_first_turns_chart(as_user, patched_db, monkeypatch):
    result = await create_chart("line", "DPS", '[{"name":"Raid","y":[1,2,3]}]')
    _quiet(monkeypatch, _stream([_tool_end("create_chart", result), {"type": "token", "text": "one"}]))
    first = _FakeSocket()
    conv_id = await _run(first, as_user, "plot")

    _quiet(monkeypatch, _stream([{"type": "token", "text": "two"}]))
    second = _FakeSocket()
    task = await ws_turn(second, as_user, conv_id)
    if task is not None:
        await task

    detail = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()
    seqs = {m["content"]: m["seq"] for m in detail["messages"] if m["role"] == "agent"}
    assert [a["message_seq"] for a in detail["artifacts"]] == [seqs["one"]]


async def ws_turn(sock, authed, conv_id):
    from backend.app.api import ws as ws_mod
    from backend.app.schemas import ChatTurn
    from backend.tests.test_proposal_ws import MODEL, _identity

    return await ws_mod._handle_turn(
        sock, ChatTurn(model=MODEL, content="again", conversation_id=uuid.UUID(str(conv_id))), _identity(authed)
    )
