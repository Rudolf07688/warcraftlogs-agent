"""The proposal frame, its link to the answer and the reload (feature 031 / sc-207 AC 1, 4, 5).

Drives ``_handle_turn`` with a fake socket and a patched ``stream_response`` over the SQLite
test DB, like test_model_fallback_ws.py. The end-to-end case runs the real participants tool
(faked WCL) and the real proposal tool, then approves over REST (design #tests).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from backend.app.agent_tools.profile_tools import propose_profile_changes
from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.schemas import ChatTurn, ProfileChangeIn
from backend.app.services import profile_proposals as proposals
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests import wcl_fakes
from backend.tests.test_participants_tool import mplus
from wcl_agent.tools.participants import get_report_participants

MODEL = "gemini-3.8-flash"


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


def _quiet(monkeypatch, stream) -> None:
    async def no_suggestions(*args, **kwargs):
        return []

    monkeypatch.setattr(ws_mod, "stream_response", stream)
    monkeypatch.setattr(ws_mod, "generate_followups", no_suggestions)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)
    monkeypatch.setattr(ws_mod.conversation_titles, "schedule_title", lambda *a, **k: None)
    monkeypatch.setattr(proposals, "schedule_character_guide", lambda *_: None)


def _tool_end(name: str, result: dict) -> dict:
    return {"type": "tool_end", "name": name, "ok": result.get("status") == "success", "args": {}, "result": result}


def _ctx_stream(make_records):
    """A scripted stream. ``make_records(ctx)`` yields the turn's records; ``ctx`` carries the
    two ToolContext attributes the proposal tool reads (ADK user_id and the session)."""

    async def stream(*args, **kwargs):
        ctx = SimpleNamespace(user_id=kwargs["user_id"], session=SimpleNamespace(id=args[1]))
        async for record in make_records(ctx):
            yield record

    return stream


async def _run(sock, authed, content="add them") -> uuid.UUID:
    task = await ws_mod._handle_turn(sock, ChatTurn(model=MODEL, content=content), _identity(authed))
    if task is not None:
        await task
    return uuid.UUID(sock.frames[0]["conversation_id"])


def _add(name: str) -> ProfileChangeIn:
    return ProfileChangeIn(action="add", target="friend", name=name, realm="Tarren Mill", region="eu")


async def test_proposal_frame_is_the_stored_proposal_before_done(as_user, patched_db, monkeypatch):
    async def records(ctx):
        result = await propose_profile_changes([_add("Kazrok"), _add("Brightmane")], ctx)
        yield _tool_end("propose_profile_changes", result)
        yield {"type": "token", "text": "Nothing changes until you approve."}

    _quiet(monkeypatch, _ctx_stream(records))
    sock = _FakeSocket()
    conv_id = await _run(sock, as_user)

    types = [f["type"] for f in sock.frames]
    assert types.index("proposal") < types.index("done")
    frame = sock.frames[types.index("proposal")]["proposal"]
    stored = await proposals.get_proposal(_identity(as_user), uuid.UUID(frame["id"]))
    assert frame == {**stored.model_dump(mode="json"), "message_seq": None}  # linked only at done
    assert [i["name"] for i in frame["items"]] == ["Kazrok", "Brightmane"]

    # At done the proposal is linked to the agent message, and the reload returns it.
    async with patched_db() as db:
        agent = [m for m in await repo.list_messages(db, conv_id, tenant_id=as_user.tenant_id) if m.role == "agent"]
    assert stored.message_seq == agent[0].seq
    detail = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()
    assert [(p["id"], p["message_seq"], p["status"]) for p in detail["proposals"]] == [
        (frame["id"], agent[0].seq, "pending")
    ]


async def test_another_tenants_proposal_id_sends_no_frame(as_user, make_authed_client, patched_db, monkeypatch):
    other = await make_authed_client("other@example.com")
    try:
        async with patched_db() as db:
            other_conv = (await repo.create_conversation(db, MODEL, tenant_id=other.tenant_id)).id
            await db.commit()
        foreign = await proposals.create_proposal(_identity(other), other_conv, [_add("Kazrok")])
    finally:
        await other.client.aclose()

    async def records(ctx):
        result = {"status": "success", "proposal": {"id": str(foreign.id)}}
        yield _tool_end("propose_profile_changes", result)
        yield {"type": "token", "text": "ok"}

    _quiet(monkeypatch, _ctx_stream(records))
    sock = _FakeSocket()
    await _run(sock, as_user)
    assert "proposal" not in [f["type"] for f in sock.frames]
    assert (await proposals.get_proposal(_identity(other), foreign.id)).message_seq is None


async def test_a_failed_turn_leaves_the_proposal_unlinked(as_user, monkeypatch):
    async def records(ctx):
        result = await propose_profile_changes([_add("Kazrok")], ctx)
        yield _tool_end("propose_profile_changes", result)
        raise RuntimeError("model fell over")

    _quiet(monkeypatch, _ctx_stream(records))
    sock = _FakeSocket()
    conv_id = await _run(sock, as_user)
    assert [f["type"] for f in sock.frames][-2:] == ["proposal", "error"]
    detail = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()
    assert [p["message_seq"] for p in detail["proposals"]] == [None]  # a standalone card

    # The next finished turn doesn't adopt it.
    async def answer(ctx):
        yield {"type": "token", "text": "Sorry about that."}

    _quiet(monkeypatch, _ctx_stream(answer))
    task = await ws_mod._handle_turn(
        _FakeSocket(), ChatTurn(conversation_id=conv_id, model=MODEL, content="again"), _identity(as_user)
    )
    await task
    detail = (await as_user.client.get(f"/api/conversations/{conv_id}")).json()
    assert [p["message_seq"] for p in detail["proposals"]] == [None]


async def test_the_identity_lives_only_for_the_turn(as_user, monkeypatch):
    # sc-222: the tool sees the turn's identity; once the turn ends (answer or error) it's gone,
    # so a task the socket starts later can't act as this user.
    seen: list = []

    def scripted(fail: bool):
        async def records(ctx):
            seen.append(current_identity.get())
            yield {"type": "token", "text": "ok"}
            if fail:
                raise RuntimeError("model fell over")

        return records

    for fail in (False, True):
        _quiet(monkeypatch, _ctx_stream(scripted(fail)))
        sock = _FakeSocket()
        await _run(sock, as_user)
        assert current_identity.get() is None
        assert ("error" in [f["type"] for f in sock.frames]) is fail
    assert [s.user_id for s in seen] == [as_user.user_id, as_user.user_id]


async def test_dungeon_except_the_shaman_end_to_end(as_user, monkeypatch):
    """The sprint's example request with fakes: resolve the run, leave out the shaman,
    propose, show the card's frame, approve, and the profile has the new friends."""
    fake = wcl_fakes.install(monkeypatch, lambda q, v: mplus())

    async def records(ctx):
        found = await get_report_participants("abc", 7)
        yield _tool_end("get_report_participants", found)
        changes = [
            ProfileChangeIn(
                action="add", target="friend", name=p["name"], realm=p["realm"], region=p["region"],
                class_name=p["class"], spec=p["spec"], played_role=p["role"],
            )
            for p in found["participants"]
            if p["class"] != "Shaman"
        ]
        yield _tool_end("propose_profile_changes", await propose_profile_changes(changes, ctx))
        yield {"type": "token", "text": "Here are the four, without the shaman. Approve to add them."}

    _quiet(monkeypatch, _ctx_stream(records))
    sock = _FakeSocket()
    await _run(sock, as_user, "add the people from the dungeon to my friends, except the shaman")
    assert len(fake.calls) == 1

    frame = next(f for f in sock.frames if f["type"] == "proposal")["proposal"]
    assert [(i["name"], i["played_role"]) for i in frame["items"]] == [
        ("Kazrok", "tank"), ("Brightmane", "healer"), ("Mira", "dps"), ("Tess", "dps")
    ]
    assert all(i["validation"]["ok"] for i in frame["items"])

    r = await as_user.client.post(f"/api/profile/proposals/{frame['id']}/approve")
    assert r.status_code == 200 and r.json()["proposal"]["status"] == "applied"
    friends = (await as_user.client.get("/api/profile")).json()["friends"]
    assert sorted(f["name"] for f in friends) == ["Brightmane", "Kazrok", "Mira", "Tess"]
    assert all(f["raid_role"] is None for f in friends)  # played role is display only (D9)
