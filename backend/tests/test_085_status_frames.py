"""085: status frames at the socket (sc-582) and the per-turn settings read (sc-583).

Scripted ``stream_response`` records through ``_start_turn`` / ``_handle_turn`` with fake sockets
over the SQLite test DB, like test_076 and test_080. Each guard is asserted where it acts: the
stored messages, the frames sent, the database scopes opened and the SQL run.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import WebSocketDisconnect
from sqlalchemy import event

from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.schemas import ChatTurn
from backend.tests.test_076_turn_serialization import BOUND_S, _frames, _messages, _scripted, _start
from backend.tests.test_080_thinking_ws import INTERIM, STATUS, _stream
from backend.tests.test_proposal_ws import MODEL, _FakeSocket, _identity, _quiet


def _count_scopes(monkeypatch) -> dict:
    """Count the tenant-scoped DB transactions ws.py opens, and how many are open right now."""
    counts = {"opened": 0, "open": 0}
    real = ws_mod.tenant_scope

    @asynccontextmanager
    async def counted(*args, **kwargs):
        counts["opened"] += 1
        counts["open"] += 1
        try:
            async with real(*args, **kwargs) as session:
                yield session
        finally:
            counts["open"] -= 1

    monkeypatch.setattr(ws_mod, "tenant_scope", counted)
    return counts


class _StallOnInterim(_FakeSocket):
    """A socket whose send of the interim frame never completes (a stalled browser)."""

    def __init__(self) -> None:
        super().__init__()
        self.sending_interim = asyncio.Event()

    async def send_json(self, payload: dict) -> None:
        if payload.get("type") == "interim":
            self.sending_interim.set()
            await asyncio.Event().wait()
        await super().send_json(payload)


async def test_a_cancel_during_the_interim_send_stores_no_retracted_text(as_user, patched_db, monkeypatch):
    # BUG-004: a second tab's turn cancels this one exactly while the interim frame is being sent.
    async def t1():
        yield {"type": "token", "text": INTERIM}
        yield {"type": "interim", "text": STATUS}
        yield {"type": "token", "text": "never"}

    async def t2():
        yield {"type": "token", "text": "Answer two"}

    _quiet(monkeypatch, _scripted({"Q1": t1, "Q2": t2}))
    scopes = _count_scopes(monkeypatch)
    stalled = _StallOnInterim()
    old = ws_mod._TurnSocket(stalled)
    first = await _start(old, as_user, "Q1")
    await asyncio.wait_for(stalled.sending_interim.wait(), BOUND_S)
    assert scopes["open"] == 0  # no DB session held across the frame send
    conv_id = uuid.UUID(_frames(old)[0]["conversation_id"])

    second = await _start(ws_mod._TurnSocket(_FakeSocket()), as_user, "Q2", conv_id)
    await asyncio.wait_for(asyncio.gather(first, second), BOUND_S)

    stored = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert stored == [("user", "Q1", "complete"), ("user", "Q2", "complete"), ("agent", "Answer two", "complete")]
    reloaded = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()["messages"]
    assert [m["content"] for m in reloaded] == [content for _, content, _ in stored]


class _DropOnToolStart(_FakeSocket):
    async def send_json(self, payload: dict) -> None:
        if payload.get("type") == "tool_start":
            raise WebSocketDisconnect(1006)
        await super().send_json(payload)


async def test_a_second_tab_during_the_partial_save_waits_and_the_save_keeps_no_retracted_text(
    as_user, patched_db, monkeypatch
):
    # The drop's partial save is under way when a second tab asks on the same chat: the save is
    # not cut short, and it holds only the text after the retraction.
    saving, finish_save = asyncio.Event(), asyncio.Event()
    real_add = repo.add_message

    async def slow_partial(session, conv_id, role, content, *args, **kwargs):
        if kwargs.get("status") == "partial":
            saving.set()
            await finish_save.wait()
        return await real_add(session, conv_id, role, content, *args, **kwargs)

    async def t1():
        yield {"type": "token", "text": INTERIM}
        yield {"type": "interim", "text": STATUS}
        yield {"type": "token", "text": "Kept so far."}
        yield {"type": "tool_start", "name": "get_report_fights", "args": {}}

    async def t2():
        yield {"type": "token", "text": "Answer two"}

    _quiet(monkeypatch, _scripted({"Q1": t1, "Q2": t2}))
    monkeypatch.setattr(repo, "add_message", slow_partial)
    old = ws_mod._TurnSocket(_DropOnToolStart())
    first = await _start(old, as_user, "Q1")
    await asyncio.wait_for(saving.wait(), BOUND_S)
    conv_id = uuid.UUID(_frames(old)[0]["conversation_id"])
    second = await _start(ws_mod._TurnSocket(_FakeSocket()), as_user, "Q2", conv_id)
    await asyncio.sleep(0.05)
    assert not second.done()  # it waits for the save, it does not cancel it
    finish_save.set()
    results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), BOUND_S)
    assert not any(isinstance(r, asyncio.CancelledError) for r in results)

    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [
        ("user", "Q1", "complete"),
        ("agent", "Kept so far.", "partial"),
        ("user", "Q2", "complete"),
        ("agent", "Answer two", "complete"),
    ]


async def _retry_frames(as_user, monkeypatch, *records) -> list[dict]:
    _quiet(monkeypatch, _stream(*records, {"type": "token", "text": "ok"}))
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content="q"), _identity(as_user))
    if task is not None:
        await task
    return [f for f in sock.frames if f["type"] in ("model_retry", "model_fallback")]


async def test_the_contract_example_retry_frame_is_sent_as_is(as_user, monkeypatch):
    # contract:chat-status-records, consumer side: the PO's example passes through unchanged.
    example = {"type": "model_retry", "attempt": 1, "max_attempts": 5, "wait_s": 4.0}
    assert await _retry_frames(as_user, monkeypatch, example) == [example]


async def test_odd_retry_numbers_still_make_a_valid_frame(as_user, monkeypatch):
    frames = await _retry_frames(
        as_user,
        monkeypatch,
        {"type": "model_retry", "attempt": 2, "max_attempts": 5, "wait_s": float("nan")},
        {"type": "model_retry", "attempt": -1, "max_attempts": -5, "wait_s": -3.0},
        {"type": "model_retry", "attempt": 3, "max_attempts": 5, "wait_s": float("inf")},
        {"type": "model_fallback", "from_model": "<b>m</b>" * 500, "to_model": "x"},
    )
    for frame in frames:
        json.dumps(frame, allow_nan=False)  # what the browser's JSON.parse accepts
    assert [(f.get("attempt"), f.get("max_attempts"), f.get("wait_s")) for f in frames[:3]] == [
        (2, 5, 0.0),
        (0, 0, 0.0),
        (3, 5, 0.0),
    ]
    assert frames[3]["from_model"] == "<b>m</b>" * 500  # shape unchanged; the browser clamps the label


async def test_thinking_frames_write_nothing_to_the_database(as_user, monkeypatch):
    # Bound: no per-frame DB write. 50 thinking frames open as many scopes as none.
    async def scopes_for(records) -> int:
        with monkeypatch.context() as m:
            counts = _count_scopes(m)
            _quiet(m, _stream(*records, {"type": "token", "text": "Answer."}))
            sock = _FakeSocket()
            task = await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content="q"), _identity(as_user))
            if task is not None:
                await task
            assert sum(f["type"] == "thinking" for f in sock.frames) == len(records)
            return counts["opened"]

    burst = [{"type": "thinking", "text": f"Step {i}."} for i in range(50)]
    assert await scopes_for(burst) == await scopes_for([])


async def test_the_preamble_reads_only_main_class_and_spec(session, tenant_id, monkeypatch):
    # sc-583 (082b): two columns of the caller's settings row, and no onboarding query.
    await repo.set_main_selection(
        session, tenant_id=tenant_id, main_class="Paladin", main_spec="Holy", main_content="raid"
    )
    await session.commit()

    async def no_whole_row(*args, **kwargs):
        raise AssertionError("the preamble must not read the whole settings row")

    monkeypatch.setattr(repo, "get_profile_settings", no_whole_row)
    statements: list[str] = []
    engine = session.bind.sync_engine if hasattr(session.bind, "sync_engine") else session.bind

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        preamble = await ws_mod._build_turn_preamble(session, tenant_id, "how did I do?")
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert "Paladin" in preamble and "Holy" in preamble
    reads = [s for s in statements if "FROM profile_settings" in s]
    assert len(reads) == 1
    columns = reads[0].split("FROM")[0]
    assert "main_class" in columns and "main_spec" in columns
    assert "main_content" not in columns and "onboarding" not in columns
