"""080: what the chat socket sends and saves for thinking and interim records (sc-569, sc-572).

Scripted ``stream_response`` records through ``_handle_turn`` / ``_start_turn`` with fake
sockets over the SQLite test DB, like test_048 and test_076. The guard takes effect on the stored
message, the knowledge-base offer and the frames sent, so those are what is asserted.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import WebSocketDisconnect

from backend.app.api import ws as ws_mod
from backend.app.kb import indexer as kb_indexer
from backend.app.schemas import STATUS_TEXT_MAX, ChatTurn
from backend.tests.test_076_turn_serialization import BOUND_S, _frames, _messages, _scripted, _sock, _start
from backend.tests.test_proposal_ws import MODEL, _FakeSocket, _identity, _quiet, _tool_end

INTERIM = "Warcraft Logs is throwing server errors on report aB3xY9's player lists. I'll retry (source 4471)."
STATUS = "Warcraft Logs is throwing server errors on report aB3xY9's player lists."
ANSWER = "Her deaths came from Gravebound."


def _stream(*records):
    async def stream(*args, **kwargs):
        for record in records:
            yield dict(record)

    return stream


def _live_answer(frames: list[dict]) -> str:
    """What the browser shows at ``done``: the tokens after the last ``interim`` frame."""
    last = max((i for i, f in enumerate(frames) if f["type"] == "interim"), default=-1)
    return "".join(f["text"] for f in frames[last + 1 :] if f["type"] == "token")


async def test_only_the_final_answer_is_saved_indexed_and_reloaded(as_user, patched_db, monkeypatch):
    offered: list[str] = []
    _quiet(monkeypatch, _stream(
        {"type": "thinking", "text": "Reading the player list."},
        {"type": "token", "text": INTERIM},
        {"type": "interim", "text": STATUS},
        {"type": "tool_start", "name": "get_report_participants", "args": {"report_code": "aB3xY9"}},
        _tool_end("get_report_participants", {"status": "success"}),
        {"type": "thinking", "text": "Comparing the deaths."},
        {"type": "token", "text": ANSWER},
    ))
    monkeypatch.setattr(kb_indexer, "offer_exchange", lambda job: offered.append(job.answer))
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content="why did she die?"), _identity(as_user))
    if task is not None:
        await task
    conv_id = uuid.UUID(sock.frames[0]["conversation_id"])

    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [
        ("user", "why did she die?", "complete"),
        ("agent", ANSWER, "complete"),
    ]
    assert offered == [ANSWER]  # the KB chat index never sees the troubleshooting
    detail = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()
    assert detail["messages"][-1]["content"] == ANSWER == _live_answer(sock.frames)  # reload = live
    # The status frames are sent as typed frames with nothing but their text.
    assert [f for f in sock.frames if f["type"] in ("thinking", "interim")] == [
        {"type": "thinking", "text": "Reading the player list."},
        {"type": "interim", "text": STATUS},
        {"type": "thinking", "text": "Comparing the deaths."},
    ]


async def test_a_turn_superseded_mid_segment_saves_what_the_live_view_held(as_user, patched_db, monkeypatch):
    # scope:080:partial-save: text not yet known to be interim is what the player saw.
    streaming = asyncio.Event()

    async def t1():
        yield {"type": "token", "text": "Looking at the pulls"}
        streaming.set()
        await asyncio.Event().wait()
        yield {"type": "token", "text": "never"}

    async def t2():
        yield {"type": "token", "text": "Answer two"}

    _quiet(monkeypatch, _scripted({"Q1": t1, "Q2": t2}))
    old, new = _sock(), _sock()
    first = await _start(old, as_user, "Q1")
    await asyncio.wait_for(streaming.wait(), BOUND_S)
    conv_id = uuid.UUID(_frames(old)[0]["conversation_id"])
    second = await _start(new, as_user, "Q2", conv_id)
    await asyncio.wait_for(asyncio.gather(first, second), BOUND_S)

    messages = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert messages[1] == ("agent", "Looking at the pulls", "partial") == ("agent", _live_answer(_frames(old)), "partial")


async def test_a_turn_superseded_after_a_retraction_saves_no_interim_text(as_user, patched_db, monkeypatch):
    in_tool_round = asyncio.Event()

    async def t1():
        yield {"type": "token", "text": INTERIM}
        yield {"type": "interim", "text": STATUS}
        yield {"type": "tool_start", "name": "get_report_participants", "args": {}}
        in_tool_round.set()
        await asyncio.Event().wait()
        yield {"type": "token", "text": "never"}

    async def t2():
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
        ("user", "Q2", "complete"),
        ("agent", "Answer two", "complete"),
    ]
    # Nothing of the superseded turn reaches the new turn's socket.
    assert not any(f.get("text") in (INTERIM, STATUS) for f in _frames(new))


class _DroppingSocket(_FakeSocket):
    """A socket that goes away when the turn's first tool card is sent."""

    async def send_json(self, payload: dict) -> None:
        if payload.get("type") == "tool_start":
            raise WebSocketDisconnect(1006)
        await super().send_json(payload)


async def test_a_dropped_socket_after_a_retraction_saves_no_interim_text(as_user, patched_db, monkeypatch):
    _quiet(monkeypatch, _stream(
        {"type": "token", "text": INTERIM},
        {"type": "interim", "text": STATUS},
        {"type": "tool_start", "name": "get_report_participants", "args": {}},
    ))
    sock = _DroppingSocket()
    try:
        await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content="why?"), _identity(as_user))
    except WebSocketDisconnect:
        pass
    conv_id = uuid.UUID(sock.frames[0]["conversation_id"])
    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [("user", "why?", "complete")]


class _ClientSocket:
    """The endpoint's view of a browser that sends one frame, then leaves."""

    def __init__(self, frame: dict) -> None:
        self.headers = {"origin": "http://localhost"}
        self.cookies: dict = {}
        self.app = None
        self.sent: list[dict] = []
        self._inbox = [frame]

    async def accept(self) -> None:
        pass

    async def close(self, code: int = 1000) -> None:
        pass

    async def receive_json(self) -> dict:
        if not self._inbox:
            raise WebSocketDisconnect(1000)
        return self._inbox.pop(0)

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


async def test_a_client_frame_of_the_new_types_starts_nothing(as_user, monkeypatch):
    started: list = []

    async def authenticated(_cookie):
        return _identity(as_user)

    async def no_turn(*args, **kwargs):
        started.append(args)

    monkeypatch.setattr(ws_mod, "origin_matches", lambda _origin: True)
    monkeypatch.setattr(ws_mod, "authenticate_session", authenticated)
    monkeypatch.setattr(ws_mod, "_start_turn", no_turn)
    for frame in ({"type": "thinking", "text": "<b>hi</b>"}, {"type": "interim", "text": "drop it"}):
        client = _ClientSocket(frame)
        await ws_mod.chat(client)
        assert started == []
        assert [f["type"] for f in client.sent] == ["error"]  # rejected as an invalid message
        assert client.sent[0]["code"] == "empty_message"


class _DropOnInterim(_FakeSocket):
    """A socket that is gone when the interim frame is sent: the browser never gets it."""

    async def send_json(self, payload: dict) -> None:
        if payload.get("type") == "interim":
            raise WebSocketDisconnect(1006)
        await super().send_json(payload)


async def test_a_drop_as_the_interim_frame_is_sent_saves_what_the_browser_kept(as_user, patched_db, monkeypatch):
    # 080 review SEC-002: the browser keeps its streamed text as the partial; so must the server,
    # or the reload would show something the server never stored.
    _quiet(monkeypatch, _stream({"type": "token", "text": INTERIM}, {"type": "interim", "text": STATUS}))
    sock = _DropOnInterim()
    try:
        await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content="why?"), _identity(as_user))
    except WebSocketDisconnect:
        pass
    conv_id = uuid.UUID(sock.frames[0]["conversation_id"])
    assert await _messages(patched_db, conv_id, as_user.tenant_id) == [
        ("user", "why?", "complete"),
        ("agent", _live_answer(sock.frames), "partial"),
    ]
    assert _live_answer(sock.frames) == INTERIM


async def test_an_over_long_status_line_is_cut_not_a_failed_turn(as_user, patched_db, monkeypatch):
    # 080 review SEC-004: the frame clamps; it never raises mid-turn.
    _quiet(monkeypatch, _stream({"type": "thinking", "text": "x" * 500}, {"type": "token", "text": ANSWER}))
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content="why?"), _identity(as_user))
    if task is not None:
        await task
    (thinking,) = [f for f in sock.frames if f["type"] == "thinking"]
    assert thinking["text"] == "x" * STATUS_TEXT_MAX
    assert sock.frames[-1]["type"] == "done"
