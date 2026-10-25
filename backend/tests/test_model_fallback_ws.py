"""Feature 021: the WebSocket turn handler around a sibling-model switch.

Drives ``_handle_turn`` with a fake socket and a patched ``stream_response`` over the
SQLite test DB (the ``as_user`` fixture), like test_ws_rate_limit.py.
"""

from __future__ import annotations

import uuid

from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.schemas import ChatTurn
from backend.app.tenancy.context import RequestIdentity
from wcl_agent.llm.model_retry import ModelRateLimited

A, B = "gemini-3.8-flash", "gemini-3.7-flash"
SWITCH = {"type": "model_fallback", "from_model": A, "to_model": B}
BOTH_BUSY = "Both Gemini flash models are rate-limited right now. Please try again in about a minute."


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


def _identity(authed) -> RequestIdentity:
    return RequestIdentity(
        user_id=authed.user_id,
        tenant_id=authed.tenant_id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


async def _messages(session_factory, conv_id: uuid.UUID, tenant_id: uuid.UUID):
    async with session_factory() as s:
        return await repo.list_messages(s, conv_id, tenant_id=tenant_id)


def _quiet(monkeypatch, stream) -> None:
    async def no_suggestions(*args, **kwargs):
        return []

    monkeypatch.setattr(ws_mod, "stream_response", stream)
    monkeypatch.setattr(ws_mod, "generate_followups", no_suggestions)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)


async def test_the_sibling_reaches_stream_response(as_user, patched_db, monkeypatch):
    seen = {}

    async def stream(*args, **kwargs):
        seen["fallback_model"] = kwargs.get("fallback_model")
        yield {"type": "token", "text": "ok"}

    _quiet(monkeypatch, stream)
    task = await ws_mod._handle_turn(
        _FakeSocket(), ChatTurn(model=A, content="q"), _identity(as_user), fallback_model=B
    )
    await task
    assert seen["fallback_model"] == B


async def test_without_a_sibling_stream_response_gets_none(as_user, patched_db, monkeypatch):
    seen = {}

    async def stream(*args, **kwargs):
        seen["fallback_model"] = kwargs.get("fallback_model", "missing")
        yield {"type": "token", "text": "ok"}

    _quiet(monkeypatch, stream)
    task = await ws_mod._handle_turn(_FakeSocket(), ChatTurn(model=A, content="q"), _identity(as_user))
    await task
    assert seen["fallback_model"] is None


async def test_start_turn_passes_the_sibling_on(monkeypatch):
    seen = {}

    async def handle(sock, turn, identity, *, fallback_model=None):
        seen["fallback_model"] = fallback_model
        return None

    monkeypatch.setattr(ws_mod, "_handle_turn", handle)
    sock = ws_mod._TurnSocket(_FakeSocket())
    await ws_mod._start_turn(sock, ChatTurn(model=A, content="q"), None, fallback_model=B)
    assert seen["fallback_model"] == B


async def test_switched_turn_stores_the_reply_once(as_user, patched_db, monkeypatch):
    """SC-003/SC-007 at the socket: text before and after the switch is stored once."""

    async def stream(*args, **kwargs):
        yield {"type": "token", "text": "Looking at the pulls. "}
        yield SWITCH
        yield {"type": "token", "text": "You wiped twice."}

    _quiet(monkeypatch, stream)
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(
        sock, ChatTurn(model=A, content="q"), _identity(as_user), fallback_model=B
    )
    await task
    assert [f["type"] for f in sock.frames] == ["meta", "token", "model_fallback", "token", "done"]
    assert sock.frames[2] == SWITCH  # the contract shape
    conv_id = uuid.UUID(sock.frames[0]["conversation_id"])
    msgs = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "q"),
        ("agent", "Looking at the pulls. You wiped twice."),
    ]


async def test_sibling_busy_too_gets_the_both_models_message(as_user, patched_db, monkeypatch):
    async def stream(*args, **kwargs):
        yield {"type": "token", "text": "partial text that must not persist"}
        yield SWITCH
        raise ModelRateLimited(2, 4.0, RuntimeError("429 RESOURCE_EXHAUSTED"))

    _quiet(monkeypatch, stream)
    sock = _FakeSocket()
    await ws_mod._handle_turn(
        sock, ChatTurn(model=A, content="q"), _identity(as_user), fallback_model=B
    )
    assert [f["type"] for f in sock.frames] == ["meta", "token", "model_fallback", "error"]
    err = sock.frames[-1]
    assert err == {"type": "error", "code": "rate_limited", "message": BOTH_BUSY}
    conv_id = uuid.UUID(sock.frames[0]["conversation_id"])
    msgs = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert [m.role for m in msgs] == ["user"]  # no partial reply persisted


async def test_no_sibling_keeps_the_feature_011_message(as_user, patched_db, monkeypatch):
    async def stream(*args, **kwargs):
        raise ModelRateLimited(5, 40.0, RuntimeError("429"))
        yield  # pragma: no cover

    _quiet(monkeypatch, stream)
    sock = _FakeSocket()
    await ws_mod._handle_turn(sock, ChatTurn(model="claude-sonnet-4-6", content="q"), _identity(as_user))
    assert sock.frames[-1] == {
        "type": "error",
        "code": "rate_limited",
        "message": ws_mod.RATE_LIMITED_MESSAGE,
    }


async def test_next_turn_after_both_busy_is_processed_normally(as_user, patched_db, monkeypatch):
    calls = {"n": 0}

    async def stream(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            yield SWITCH
            raise ModelRateLimited(2, 4.0, RuntimeError("429"))
        yield {"type": "token", "text": "All good now."}

    _quiet(monkeypatch, stream)
    identity = _identity(as_user)
    first = _FakeSocket()
    await ws_mod._handle_turn(first, ChatTurn(model=A, content="q1"), identity, fallback_model=B)
    assert first.frames[-1]["message"] == BOTH_BUSY
    conv_id = uuid.UUID(first.frames[0]["conversation_id"])

    second = _FakeSocket()
    task = await ws_mod._handle_turn(
        second, ChatTurn(conversation_id=conv_id, model=A, content="q2"), identity, fallback_model=B
    )
    await task
    assert [f["type"] for f in second.frames] == ["meta", "token", "done"]
    msgs = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "q1"),
        ("user", "q2"),
        ("agent", "All good now."),
    ]
