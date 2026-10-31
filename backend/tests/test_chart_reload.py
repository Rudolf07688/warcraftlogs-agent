"""sc-213: a chart made in a chat comes back when the chat is reopened.

Drives ``_handle_turn`` with a fake socket and a scripted stream (like test_proposal_ws.py)
over the SQLite test DB: the real ``create_chart`` result is captured as the turn runs, then
``GET /api/conversations/{id}`` must return it under the agent message with a Plotly figure.
"""

from __future__ import annotations

import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.db import repository as repo
from backend.tests.test_proposal_ws import _FakeSocket, _quiet, _run, _tool_end
from wcl_agent.llm.model_retry import ModelRateLimited
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


# --- sc-213 / SPEC-002: a turn that does not complete still links its charts ----------------


def _failing_stream(records, exc):
    async def stream(*args, **kwargs):
        for r in records:
            yield r
        raise exc

    return stream


async def _interrupted_turn(monkeypatch, as_user, exc, *, tokens=True):
    result = await create_chart("line", "DPS", '[{"name":"Raid","y":[1,2,3]}]')
    records = [_tool_end("create_chart", result)]
    if tokens:
        records.append({"type": "token", "text": "Half an answ"})
    _quiet(monkeypatch, _failing_stream(records, exc))
    sock = _FakeSocket()
    try:
        await _run(sock, as_user, "plot dps")
    except WebSocketDisconnect:
        pass
    return uuid.UUID(sock.frames[0]["conversation_id"])


async def _follow_with_a_completed_turn(monkeypatch, as_user, conv_id):
    _quiet(monkeypatch, _stream([{"type": "token", "text": "next answer"}]))
    task = await ws_turn(_FakeSocket(), as_user, conv_id)
    if task is not None:
        await task


async def _detail(as_user, conv_id):
    return (await as_user.client.get(f"/api/conversations/{conv_id}")).json()


@pytest.mark.parametrize("exc", [WebSocketDisconnect(), RuntimeError("model fell over")])
async def test_an_interrupted_turn_links_its_chart_to_the_partial_answer(as_user, monkeypatch, exc):
    conv_id = await _interrupted_turn(monkeypatch, as_user, exc)
    detail = await _detail(as_user, conv_id)
    partial = next(m for m in detail["messages"] if m["role"] == "agent")
    assert partial["status"] == "partial"
    assert [a["message_seq"] for a in detail["artifacts"]] == [partial["seq"]]  # renders under it

    await _follow_with_a_completed_turn(monkeypatch, as_user, conv_id)  # does not take it
    detail = await _detail(as_user, conv_id)
    assert [a["message_seq"] for a in detail["artifacts"]] == [partial["seq"]]


@pytest.mark.parametrize(
    ("exc", "tokens"),
    [
        (ModelRateLimited(5, 40.0, RuntimeError("429")), True),  # no message is saved
        (RuntimeError("fell over before any text"), False),  # nothing to save
        (WebSocketDisconnect(), False),
    ],
)
async def test_a_turn_with_no_saved_answer_anchors_its_chart_to_its_question(
    as_user, monkeypatch, exc, tokens
):
    conv_id = await _interrupted_turn(monkeypatch, as_user, exc, tokens=tokens)
    detail = await _detail(as_user, conv_id)
    question = next(m for m in detail["messages"] if m["role"] == "user")
    assert not [m for m in detail["messages"] if m["role"] == "agent"]
    assert [a["message_seq"] for a in detail["artifacts"]] == [question["seq"]]

    await _follow_with_a_completed_turn(monkeypatch, as_user, conv_id)
    detail = await _detail(as_user, conv_id)
    answer = next(m for m in detail["messages"] if m["role"] == "agent")
    assert [a["message_seq"] for a in detail["artifacts"]] == [question["seq"]]
    assert question["seq"] != answer["seq"]  # never claimed by the later answer
