"""The chat-turn path: short transactions, fewer reads, fewer frames (PERF-005/006/007/008/013/016)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from backend.app import agent_runner
from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.schemas import ChatTurn
from backend.app.services import raids as raids_service
from backend.app.tenancy.context import RequestIdentity


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


def _identity(tenant_id) -> RequestIdentity:
    return RequestIdentity(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


async def test_no_transaction_is_open_while_the_model_streams(as_user, patched_db, monkeypatch):
    open_sessions = {"n": 0}
    real_scope = ws_mod.tenant_scope

    @asynccontextmanager
    async def counting_scope(*args, **kwargs):
        async with real_scope(*args, **kwargs) as session:
            open_sessions["n"] += 1
            try:
                yield session
            finally:
                open_sessions["n"] -= 1

    seen_during_stream: list[int] = []

    async def stream(*args, **kwargs):
        seen_during_stream.append(open_sessions["n"])
        yield {"type": "token", "text": "Hello"}
        seen_during_stream.append(open_sessions["n"])
        yield {"type": "tool_end", "name": "get_report_fights", "ok": False, "args": {}, "result": {}}
        seen_during_stream.append(open_sessions["n"])

    async def suggest(*args, **kwargs):
        return ["Next?"]

    monkeypatch.setattr(ws_mod, "tenant_scope", counting_scope)
    monkeypatch.setattr(ws_mod, "stream_response", stream)
    monkeypatch.setattr(ws_mod, "generate_followups", suggest)
    monkeypatch.setattr(ws_mod, "set_cache_scope", lambda *_: None)
    sock = _FakeSocket()

    await ws_mod._handle_turn(sock, ChatTurn(model="gemini-3.6-flash", content="hi"), _identity(as_user.tenant_id))

    assert seen_during_stream == [0, 0, 0]  # PERF-006: no connection held across the stream
    types = [f["type"] for f in sock.frames]
    assert types == ["meta", "token", "tool_end", "done", "suggestions"]  # PERF-005 order
    done, suggestions = sock.frames[-2], sock.frames[-1]
    assert suggestions["message_id"] == done["message_id"]
    assert suggestions["suggestions"] == ["Next?"]


async def test_add_message_titles_without_loading_the_transcript(session, tenant_id, monkeypatch):
    async def boom(*args, **kwargs):
        raise AssertionError("add_message must not load the conversation with its messages")

    conv = await repo.create_conversation(session, model="gemini-3.6-flash", tenant_id=tenant_id)
    await session.commit()
    monkeypatch.setattr(repo, "get_conversation", boom)
    await repo.add_message(session, conv.id, "user", "Why did we wipe on Gnarlroot?", tenant_id=tenant_id)
    await repo.add_message(session, conv.id, "agent", "Because…", tenant_id=tenant_id)
    await repo.add_message(session, conv.id, "user", "And the second pull?", tenant_id=tenant_id)
    await session.commit()
    row = await repo.get_conversation_row(session, conv.id, tenant_id=tenant_id)
    assert row.title == "Why did we wipe on Gnarlroot?"  # the first user message only


async def test_raid_tracked_only_for_new_raids_and_fights_label_needs_no_metadata_call(
    patched_db, tenant_id, monkeypatch
):
    def no_metadata(code):
        raise AssertionError("get_report_fights already carries the label fields (PERF-016)")

    monkeypatch.setattr(raids_service, "get_report_metadata", no_metadata)
    record = {
        "name": "get_report_fights",
        "ok": True,
        "args": {"report_code": "NEWRAID"},
        "result": {
            "status": "success",
            "title": "Raid night",
            "zone": {"id": 1, "name": "Liberation"},
            "guild": "Horde",
            "start_time_ms": 1_760_000_000_000,
            "fights": [],
        },
    }
    identity = _identity(tenant_id)
    first, second = _FakeSocket(), _FakeSocket()
    await ws_mod._handle_tool_end(first, record, None, identity)
    await ws_mod._handle_tool_end(second, record, None, identity)

    tracked = [f for f in first.frames if f["type"] == "raid_tracked"]
    assert len(tracked) == 1 and tracked[0]["label"].startswith("Horde — Liberation — ")
    assert not any(f["type"] == "raid_tracked" for f in second.frames)  # PERF-013


async def test_list_tracked_raids_limit(session, tenant_id):
    for i in range(5):
        await repo.upsert_tracked_raid(session, tenant_id=tenant_id, report_code=f"R{i}", label=f"R{i}")
    await session.commit()
    assert len(await repo.list_tracked_raids(session, tenant_id=tenant_id, limit=3)) == 3
    assert len(await repo.list_tracked_raids(session, tenant_id=tenant_id)) == 5


async def test_ensure_session_checks_existence_without_loading_events(monkeypatch):
    seen = {}

    class _Service:
        async def get_session(self, *, app_name, user_id, session_id, config=None):
            seen["config"] = config
            return object()

        async def create_session(self, **kwargs):  # pragma: no cover - session exists
            raise AssertionError

    monkeypatch.setattr(agent_runner, "_get_session_service", lambda: _Service())
    await agent_runner._ensure_session("s1", "u1")
    assert seen["config"] is not None and seen["config"].num_recent_events == 0  # PERF-008
