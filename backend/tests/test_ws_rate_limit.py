"""Feature 011 / US1: the WebSocket turn handler on model rate limits.

Drives ``_handle_turn`` directly with a fake socket (collects ``send_json`` payloads) and a
patched ``stream_response``, over the SQLite test DB via the ``as_user`` fixture — so the
real conversation/message persistence runs, without a WebSocket transport.
"""

from __future__ import annotations

import uuid

from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.schemas import ChatTurn
from backend.app.tenancy.context import RequestIdentity
from wcl_agent.model_retry import ModelRateLimited


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


async def test_rate_limited_turn_sends_frames_and_persists_no_partial(
    as_user, patched_db, monkeypatch
):
    async def rate_limited_stream(*args, **kwargs):
        yield {"type": "model_retry", "attempt": 1, "max_attempts": 5, "wait_s": 2.0}
        yield {"type": "token", "text": "partial text that must not persist"}
        raise ModelRateLimited(5, 40.0, RuntimeError("429 RESOURCE_EXHAUSTED"))

    monkeypatch.setattr(ws_mod, "stream_response", rate_limited_stream)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)
    sock = _FakeSocket()
    turn = ChatTurn(conversation_id=None, model="gemini-3.6-flash", content="How did we do?")

    await ws_mod._handle_turn(sock, turn, _identity(as_user))

    types = [f["type"] for f in sock.frames]
    assert types == ["meta", "model_retry", "token", "error"]
    retry = sock.frames[1]
    assert retry == {"type": "model_retry", "attempt": 1, "max_attempts": 5, "wait_s": 2.0}
    err = sock.frames[-1]
    assert err["code"] == "rate_limited"
    assert err["message"] == ws_mod.RATE_LIMITED_MESSAGE
    assert "429" not in err["message"] and "RESOURCE_EXHAUSTED" not in err["message"]

    conv_id = uuid.UUID(sock.frames[0]["conversation_id"])
    msgs = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert [m.role for m in msgs] == ["user"]  # FR-005: no partial agent reply persisted


async def test_next_turn_after_rate_limit_is_processed_normally(as_user, patched_db, monkeypatch):
    calls = {"n": 0}

    async def stream(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModelRateLimited(5, 40.0, RuntimeError("429"))
            yield  # pragma: no cover
        yield {"type": "token", "text": "All good now."}

    async def no_suggestions(*args, **kwargs):
        return []

    monkeypatch.setattr(ws_mod, "stream_response", stream)
    monkeypatch.setattr(ws_mod, "generate_followups", no_suggestions)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)
    identity = _identity(as_user)

    first = _FakeSocket()
    await ws_mod._handle_turn(first, ChatTurn(model="gemini-3.6-flash", content="q1"), identity)
    assert first.frames[-1]["code"] == "rate_limited"
    conv_id = uuid.UUID(first.frames[0]["conversation_id"])

    second = _FakeSocket()
    task = await ws_mod._handle_turn(
        second, ChatTurn(conversation_id=conv_id, model="gemini-3.6-flash", content="q2"), identity
    )
    await task  # the background suggestions (none here) finish without a frame
    assert [f["type"] for f in second.frames] == ["meta", "token", "done"]
    msgs = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "q1"),
        ("user", "q2"),
        ("agent", "All good now."),
    ]


async def test_other_errors_keep_agent_error_and_partial(as_user, patched_db, monkeypatch):
    async def broken(*args, **kwargs):
        yield {"type": "token", "text": "half an answer"}
        raise RuntimeError("vertex exploded")

    monkeypatch.setattr(ws_mod, "stream_response", broken)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)
    sock = _FakeSocket()
    await ws_mod._handle_turn(sock, ChatTurn(model="gemini-3.6-flash", content="q"), _identity(as_user))
    assert sock.frames[-1]["code"] == "agent_error"
    conv_id = uuid.UUID(sock.frames[0]["conversation_id"])
    msgs = await _messages(patched_db, conv_id, as_user.tenant_id)
    assert [(m.role, m.status) for m in msgs] == [("user", "complete"), ("agent", "partial")] or [
        m.role for m in msgs
    ] == ["user", "agent"]
