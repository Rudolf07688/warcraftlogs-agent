"""A no-answer turn is saved for the user, and nothing else learns from it (048, QA BUG-002).

The runner marks its closing no-answer message (``empty``); the chat socket saves it as the
reply but never offers it to the knowledge-base indexer, names the chat after it, or predicts
follow-ups from it. Drives ``stream_response`` with synthetic ADK events and ``_handle_turn``
with a fake socket over the SQLite test DB: no model call.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from backend.app import agent_runner
from backend.app.agent_runner import EMPTY_ANSWER_MESSAGE
from backend.app.api import ws as ws_mod
from backend.app.db.models import Message
from backend.app.kb import indexer as kb_indexer
from backend.app.schemas import ChatTurn
from backend.app.services import conversation_titles
from backend.app.tenancy.context import RequestIdentity
from backend.tests.test_046_empty_turn import CHAT_USER, _event, _interim_then_tools, _part, _Runner

INTERIM = "Let me get the totals."


async def _records(monkeypatch, events, user_id=CHAT_USER) -> list[dict]:
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _Runner(events))

    async def _noop(_session_id, _user_id=None):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", _noop)
    return [r async for r in agent_runner.stream_response("m", "s", "hi", user_id=user_id)]


async def test_the_runner_marks_only_its_no_answer_message(monkeypatch):
    records = await _records(monkeypatch, [*_interim_then_tools(), _event(_part(text=""), final=True)])
    tokens = [r for r in records if r["type"] == "token"]
    assert tokens[0] == {"type": "token", "text": INTERIM}
    assert tokens[-1] == {"type": "token", "text": "\n\n" + EMPTY_ANSWER_MESSAGE, "empty": True}


async def test_an_answered_turn_carries_no_mark(monkeypatch):
    records = await _records(monkeypatch, [_event(_part(text="Hello"), partial=True), _event(_part(text="Hello"), final=True)])
    assert [r for r in records if r["type"] == "token"] == [{"type": "token", "text": "Hello"}]


# --- The chat socket's final save --------------------------------------------------------


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


@pytest.fixture
def after_save(patched_db, monkeypatch):
    """Records what the socket hands on after saving: the exchange, the title job, follow-ups."""
    seen: dict[str, list] = {"exchange": [], "title": [], "followups": []}

    async def followups(model, question, answer):
        seen["followups"].append(answer)
        return []

    monkeypatch.setattr(kb_indexer, "offer_exchange", lambda job: seen["exchange"].append(job.answer))
    monkeypatch.setattr(conversation_titles, "schedule_title", lambda *a, **k: seen["title"].append(a[3]))
    monkeypatch.setattr(ws_mod, "generate_followups", followups)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)
    return seen


def _stream(*records):
    async def stream(*args, **kwargs):
        for record in records:
            yield dict(record)

    return stream


async def _turn(monkeypatch, as_user, *records):
    monkeypatch.setattr(ws_mod, "stream_response", _stream(*records))
    sock = _FakeSocket()
    identity = RequestIdentity(user_id=as_user.user_id, tenant_id=as_user.tenant_id, membership_role="tenant_admin",
                               is_platform_admin=False, session_id=uuid.uuid4())
    task = await ws_mod._handle_turn(sock, ChatTurn(model="gemini-3.6-flash", content="top damage?"), identity)
    if task is not None:
        await task
    return sock, task


async def _saved_answer(patched_db) -> str:
    async with patched_db() as s:
        return await s.scalar(select(Message.content).where(Message.role == "agent"))


async def test_a_no_answer_turn_is_saved_but_never_indexed_titled_or_followed_up(
    as_user, patched_db, after_save, monkeypatch
):
    closing = "\n\n" + EMPTY_ANSWER_MESSAGE
    sock, task = await _turn(
        monkeypatch, as_user,
        {"type": "token", "text": INTERIM},
        {"type": "token", "text": closing, "empty": True},
    )
    assert await _saved_answer(patched_db) == INTERIM + closing  # the user still sees why
    assert after_save == {"exchange": [], "title": [], "followups": []}
    assert task is None
    assert [f for f in sock.frames if f["type"] == "token"] == [
        {"type": "token", "text": INTERIM},
        {"type": "token", "text": closing},  # the wire frame is unchanged: no internal flag
    ]
    assert any(f["type"] == "done" for f in sock.frames)


async def test_an_answered_turn_is_indexed_titled_and_followed_up(as_user, patched_db, after_save, monkeypatch):
    await _turn(monkeypatch, as_user, {"type": "token", "text": "Vagxsu topped damage."})
    assert await _saved_answer(patched_db) == "Vagxsu topped damage."
    assert after_save == {
        "exchange": ["Vagxsu topped damage."],
        "title": ["Vagxsu topped damage."],
        "followups": ["Vagxsu topped damage."],
    }
