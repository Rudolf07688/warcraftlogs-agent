"""sc-511: one turn at a time per chat, across sockets.

A dropped socket is noticed only when a send fails, so its turn (T1) can still be in a tool
round when the player asks again on a new socket (T2). T2 supersedes T1: T1 is cut short and
saves its partial before T2 writes, so the chat reads Q1, partial A1, Q2, A2 and each turn's
charts stay with its own answer. Drives ``_start_turn`` (the receive loop's step) with fake
sockets and a scripted stream over the SQLite test DB, like test_proposal_ws.py.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.schemas import ChatTurn
from backend.tests.test_proposal_ws import MODEL, _FakeSocket, _identity, _quiet, _tool_end
from wcl_agent.tools.tools import create_chart

# Generous against a slow runner; a turn that never ends fails the test instead of hanging it.
BOUND_S = 5.0


def _sock() -> ws_mod._TurnSocket:
    return ws_mod._TurnSocket(_FakeSocket())


def _frames(sock: ws_mod._TurnSocket) -> list[dict]:
    return sock.ws.frames


async def _start(sock, authed, content, conv_id=None) -> asyncio.Task:
    turn = ChatTurn(model=MODEL, content=content, conversation_id=conv_id)
    return asyncio.create_task(ws_mod._start_turn(sock, turn, _identity(authed)))


async def _messages(patched_db, conv_id, tenant_id) -> list[tuple[str, str, str]]:
    async with patched_db() as db:
        rows = await repo.list_messages(db, conv_id, tenant_id=tenant_id)
    return [(m.role, m.content, m.status) for m in rows]


async def _chart(title: str) -> dict:
    result = await create_chart("bar", title, '[{"name":"Raid","x":["A"],"y":[1]}]')
    return _tool_end("create_chart", result)


def _scripted(scripts):
    """``stream_response`` that runs ``scripts[user_text]()`` for each turn."""

    async def stream(*args, **kwargs):
        async for record in scripts[args[2]]():
            yield record

    return stream


async def test_a_new_turn_cuts_short_a_dropped_turn_mid_tool_round(
    as_user, patched_db, monkeypatch
):
    # The story's acceptance: T1 is mid tool round when its socket goes quiet; T2 starts on a
    # new socket for the same chat. T1 ends before T2 writes; Q1, partial A1, Q2, A2; charts
    # stay with their own answer.
    chart_1, chart_2 = await _chart("T1 chart"), await _chart("T2 chart")
    in_tool_round = asyncio.Event()

    async def t1():
        yield {"type": "token", "text": "Looking at the pulls"}
        yield chart_1
        yield {"type": "tool_start", "name": "get_report_fights", "args": {}}
        in_tool_round.set()
        await asyncio.Event().wait()  # the tool never returns
        yield {"type": "token", "text": "never"}

    async def t2():
        yield chart_2
        yield {"type": "token", "text": "Answer two"}

    _quiet(monkeypatch, _scripted({"Q1": t1, "Q2": t2}))
    old, new = _sock(), _sock()
    first = await _start(old, as_user, "Q1")
    await asyncio.wait_for(in_tool_round.wait(), BOUND_S)
    conv_id = uuid.UUID(_frames(old)[0]["conversation_id"])

    second = await _start(new, as_user, "Q2", conv_id)
    await asyncio.wait_for(asyncio.gather(first, second), BOUND_S)

    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [
        ("user", "Q1", "complete"),
        ("agent", "Looking at the pulls", "partial"),
        ("user", "Q2", "complete"),
        ("agent", "Answer two", "complete"),
    ]
    detail = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()
    seq = {m["content"]: m["seq"] for m in detail["messages"]}
    assert sorted((a["title"], a["message_seq"]) for a in detail["artifacts"]) == [
        ("T1 chart", seq["Looking at the pulls"]),
        ("T2 chart", seq["Answer two"]),
    ]
    # The old socket is told (a live second tab unlocks) and its receive loop goes on.
    assert _frames(old)[-1]["type"] == "error" and _frames(old)[-1]["code"] == "superseded"
    assert first.result() is None and old.suggestions is None
    assert [f["type"] for f in _frames(new)][-1] == "done"
    assert ws_mod._ChatTurn.turns == {}


async def test_a_turn_that_will_not_end_delays_the_next_one_only_boundedly(
    as_user, patched_db, monkeypatch
):
    # Liveness: T1's clean-up hangs (as when a tool ignores cancellation and the stream's
    # producer can't be reaped). T2 waits SUPERSEDE_WAIT_S, then answers; T1, no longer holding
    # the chat, saves nothing when it finally ends. T2 waits with no DB connection held
    # (076 review SEC-001).
    monkeypatch.setattr(ws_mod, "SUPERSEDE_WAIT_S", 0.5)
    stuck, release = asyncio.Event(), asyncio.Event()
    open_scopes = [0]
    open_while_waiting: list[int] = []
    real_scope = ws_mod.tenant_scope

    @asynccontextmanager
    async def counted_scope(*args, **kwargs):
        open_scopes[0] += 1
        try:
            async with real_scope(*args, **kwargs) as session:
                yield session
        finally:
            open_scopes[0] -= 1

    async def t1():
        yield {"type": "token", "text": "partial one"}
        try:
            stuck.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:  # T2 cancelled us and is waiting now
            open_while_waiting.append(open_scopes[0])
            await release.wait()
            raise
        yield {"type": "token", "text": "never"}

    async def t2():
        yield {"type": "token", "text": "Answer two"}

    _quiet(monkeypatch, _scripted({"Q1": t1, "Q2": t2}))
    monkeypatch.setattr(ws_mod, "tenant_scope", counted_scope)
    old = _sock()
    first = await _start(old, as_user, "Q1")
    await asyncio.wait_for(stuck.wait(), BOUND_S)
    conv_id = uuid.UUID(_frames(old)[0]["conversation_id"])

    await asyncio.wait_for(await _start(_sock(), as_user, "Q2", conv_id), BOUND_S)
    assert open_while_waiting == [0]
    assert not first.done()
    release.set()
    await asyncio.wait_for(first, BOUND_S)

    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [
        ("user", "Q1", "complete"),
        ("user", "Q2", "complete"),
        ("agent", "Answer two", "complete"),
    ]
    assert ws_mod._ChatTurn.turns == {}


async def test_a_save_that_outlasts_the_wait_writes_nothing(as_user, patched_db, monkeypatch):
    # 076 review SEC-002: T1 has finished streaming and is saving (not cancellable) when T2
    # arrives; its save outlasts SUPERSEDE_WAIT_S, so T2 goes on. T1 then finds the chat taken
    # over inside its save transaction and rolls back: no A1 after Q2.
    monkeypatch.setattr(ws_mod, "SUPERSEDE_WAIT_S", 0.5)
    saving, finish_save = asyncio.Event(), asyncio.Event()
    real_add = repo.add_message

    async def slow_answer_one(session, conv_id, role, content, *args, **kwargs):
        if content == "Answer one":
            saving.set()
            await finish_save.wait()
        return await real_add(session, conv_id, role, content, *args, **kwargs)

    async def t1():
        yield {"type": "token", "text": "Answer one"}

    async def t2():
        yield {"type": "token", "text": "Answer two"}

    _quiet(monkeypatch, _scripted({"Q1": t1, "Q2": t2}))
    monkeypatch.setattr(repo, "add_message", slow_answer_one)
    old = _sock()
    first = await _start(old, as_user, "Q1")
    await asyncio.wait_for(saving.wait(), BOUND_S)
    conv_id = uuid.UUID(_frames(old)[0]["conversation_id"])

    await asyncio.wait_for(await _start(_sock(), as_user, "Q2", conv_id), BOUND_S)
    finish_save.set()
    await asyncio.wait_for(first, BOUND_S)

    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [
        ("user", "Q1", "complete"),
        ("user", "Q2", "complete"),
        ("agent", "Answer two", "complete"),
    ]
    assert [(f["type"], f.get("code")) for f in _frames(old)][-1] == ("error", "superseded")
    assert ws_mod._ChatTurn.turns == {}


async def test_a_failing_partial_save_does_not_close_the_superseded_socket(
    as_user, patched_db, monkeypatch
):
    # 076 review SEC-003: the superseded turn's partial save raises; the cancel still ends the
    # turn, the old socket's receive loop goes on and is told, and T2 answers.
    in_tool_round = asyncio.Event()

    async def t1():
        yield {"type": "token", "text": "partial one"}
        in_tool_round.set()
        await asyncio.Event().wait()
        yield {"type": "token", "text": "never"}

    async def t2():
        yield {"type": "token", "text": "Answer two"}

    async def partial_fails(*args, **kwargs):
        raise RuntimeError("db down")

    _quiet(monkeypatch, _scripted({"Q1": t1, "Q2": t2}))
    monkeypatch.setattr(ws_mod, "_persist_partial", partial_fails)
    old, new = _sock(), _sock()
    first = await _start(old, as_user, "Q1")
    await asyncio.wait_for(in_tool_round.wait(), BOUND_S)
    conv_id = uuid.UUID(_frames(old)[0]["conversation_id"])

    second = await _start(new, as_user, "Q2", conv_id)
    await asyncio.wait_for(asyncio.gather(first, second), BOUND_S)
    assert first.result() is None  # nothing escaped into the receive loop
    assert _frames(old)[-1]["code"] == "superseded"
    assert [f["type"] for f in _frames(new)][-1] == "done"
    assert ws_mod._ChatTurn.turns == {}


async def test_another_workspace_cannot_touch_a_chats_turn(
    as_user, make_authed_client, patched_db, monkeypatch
):
    # Workspace B sends workspace A's conversation id while A's turn is in a tool round: B gets
    # not-found, A's turn is neither cancelled nor delayed and completes, nothing of B is written.
    other = await make_authed_client("other@example.com")
    await other.client.aclose()
    in_tool_round, tool_returns = asyncio.Event(), asyncio.Event()

    async def a_turn():
        yield {"type": "token", "text": "Answer A, "}
        in_tool_round.set()
        await tool_returns.wait()
        yield {"type": "token", "text": "complete."}

    async def b_turn():
        yield {"type": "token", "text": "B was here"}

    _quiet(monkeypatch, _scripted({"QA": a_turn, "QB": b_turn}))
    a_sock, b_sock = _sock(), _sock()
    a_task = await _start(a_sock, as_user, "QA")
    await asyncio.wait_for(in_tool_round.wait(), BOUND_S)
    conv_id = uuid.UUID(_frames(a_sock)[0]["conversation_id"])

    await asyncio.wait_for(await _start(b_sock, other, "QB", conv_id), BOUND_S)
    assert [(f["type"], f.get("code")) for f in _frames(b_sock)] == [("error", "not_found")]
    assert not a_task.done()

    tool_returns.set()
    await asyncio.wait_for(a_task, BOUND_S)
    assert [f["type"] for f in _frames(a_sock)][-1] == "done"
    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [
        ("user", "QA", "complete"),
        ("agent", "Answer A, complete.", "complete"),
    ]
    async with patched_db() as db:
        assert await repo.list_conversations(db, tenant_id=other.tenant_id) == []


async def test_the_registry_is_empty_after_many_turns_that_fail(as_user, monkeypatch):
    # Every way a turn ends releases its chat: answers, stream errors and failed setups.
    async def answer():
        yield {"type": "token", "text": "ok"}

    async def fails():
        yield {"type": "token", "text": "half"}
        raise RuntimeError("model fell over")

    async def setup_fails(*args, **kwargs):
        raise RuntimeError("preamble failed")

    _quiet(monkeypatch, _scripted({"ok": answer, "fail": fails}))
    for i in range(100):
        content = ("ok", "fail", "setup")[i % 3]
        with monkeypatch.context() as m:
            if content == "setup":
                m.setattr(ws_mod, "_build_turn_preamble", setup_fails)
            task = await _start(_sock(), as_user, content if content != "setup" else "ok")
            try:
                await asyncio.wait_for(task, BOUND_S)
            except RuntimeError:
                pass
    assert ws_mod._ChatTurn.turns == {}
