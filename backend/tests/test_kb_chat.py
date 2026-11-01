"""Past conversations in the knowledge base (feature 043, sc-305): the chat socket queues one
exchange per completed turn, without tool payloads, and never waits for the embedding.

Drives ``_handle_turn`` with a fake socket and a patched ``stream_response`` over the SQLite
test DB (like test_ws_rate_limit.py), with a real indexer and a fake embedder.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from backend.app.api import ws as ws_mod
from backend.app.db.models import KbChatChunk, Message
from backend.app.kb import indexer as kb_indexer
from backend.app.kb.chat_chunker import ExchangeJob, chunk_exchange
from backend.app.kb.chunks import MAX_CHAT_TEXT
from backend.app.kb.embedder import DIMENSIONS, set_embedder
from backend.app.kb.indexer import KbIndexer
from backend.app.schemas import ChatTurn
from backend.app.tenancy.context import RequestIdentity
from wcl_agent.llm.model_retry import ModelRateLimited

TOOL_PAYLOAD = "SECRET-TOOL-PAYLOAD-damageDone-139100000"


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


class BlockingEmbedder:
    """Holds every embed call until released, so a test can prove nobody waits for it."""

    model = "fake-embed"

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.calls: list[list[str]] = []

    async def embed(self, texts, *, task):
        self.calls.append(list(texts))
        await self.release.wait()
        return [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]


def _identity(authed) -> RequestIdentity:
    return RequestIdentity(user_id=authed.user_id, tenant_id=authed.tenant_id, membership_role="tenant_admin",
                           is_platform_admin=False, session_id=uuid.uuid4())


@pytest.fixture
async def indexer(patched_db, monkeypatch):
    async def no_suggestions(*args, **kwargs):
        return []

    monkeypatch.setattr(ws_mod, "generate_followups", no_suggestions)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)
    embedder = BlockingEmbedder()
    set_embedder(embedder)
    running = KbIndexer(max_items=10, batch=8, sweep_s=600)
    running.start()
    running.embedder = embedder
    yield running
    embedder.release.set()
    await running.stop(grace_s=2)
    set_embedder(None)


async def chat_rows(patched_db):
    async with patched_db() as s:
        return list(await s.scalars(select(KbChatChunk)))


async def wait_for(predicate, tries: int = 200):
    for _ in range(tries):
        if await predicate():
            return True
        await asyncio.sleep(0.01)
    return False


def stream_of(*records, error: Exception | None = None):
    async def stream(*args, **kwargs):
        for record in records:
            yield record
        if error is not None:
            raise error

    return stream


async def test_a_completed_turn_queues_one_exchange_without_tool_payloads(as_user, patched_db, indexer, monkeypatch):
    monkeypatch.setattr(ws_mod, "stream_response", stream_of(
        {"type": "token", "text": "Vagxsu did "},
        {"type": "tool_start", "name": "get_report_table", "args": {"report_code": "ABC"}},
        {"type": "tool_end", "name": "get_report_table", "ok": False, "args": {}, "result": {"raw": TOOL_PAYLOAD}},
        {"type": "token", "text": "139.1M damage."},
    ))
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(sock, ChatTurn(model="gemini-3.6-flash", content="How did Vagxsu do?"),
                                     _identity(as_user))
    if task is not None:
        await task
    # The turn finished while the embedder is still blocked: nobody waited for it.
    assert any(f["type"] == "done" for f in sock.frames)
    # Don't poll the DB while the indexer writes: the SQLite test engine shares one connection,
    # so a reader's rollback could undo its open transaction. An embed call means the chunk
    # was committed first.
    assert await wait_for(lambda: _called(indexer.embedder))
    assert not indexer.embedder.release.is_set()
    [row] = await chat_rows(patched_db)
    assert row.text == "Question: How did Vagxsu do?\n\nAnswer: Vagxsu did 139.1M damage."
    assert TOOL_PAYLOAD not in row.text and "get_report_table" not in row.text
    async with patched_db() as s:
        answer = await s.scalar(select(Message).where(Message.conversation_id == row.conversation_id,
                                                      Message.seq == row.message_seq))
    assert answer.role == "agent" and answer.content == "Vagxsu did 139.1M damage."
    assert row.tenant_id == as_user.tenant_id and row.embedding is None
    indexer.embedder.release.set()
    await indexer.stop(grace_s=2)  # drains the job, commit included
    [row] = await chat_rows(patched_db)
    assert row.embedding is not None and row.embed_model == "fake-embed"


async def _called(embedder) -> bool:
    return bool(embedder.calls)


@pytest.mark.parametrize(
    "records,error",
    [
        ([{"type": "token", "text": "half an ans"}], RuntimeError("agent blew up")),  # partial + error
        ([{"type": "token", "text": "half"}], ModelRateLimited(5, 40.0, RuntimeError("429"))),
        ([], None),  # no streamed text at all: "(no response)" is not an answer worth keeping
    ],
)
async def test_failed_interrupted_or_empty_turns_queue_nothing(as_user, patched_db, indexer, monkeypatch, records, error):
    monkeypatch.setattr(ws_mod, "stream_response", stream_of(*records, error=error))
    sock = _FakeSocket()
    task = await ws_mod._handle_turn(sock, ChatTurn(model="gemini-3.6-flash", content="q"), _identity(as_user))
    if task is not None:
        await task
    await indexer.stop(grace_s=2)
    assert await chat_rows(patched_db) == [] and indexer.embedder.calls == []


def test_exchange_text_is_bounded_and_labelled():
    job = ExchangeJob(uuid.uuid4(), uuid.uuid4(), 4, "  what   did we say about my arms build last week, in detail please?  ",
                      "x " * 5000, None)  # type: ignore[arg-type]
    draft = chunk_exchange(job)
    assert len(draft.text) <= MAX_CHAT_TEXT and draft.text.startswith("Question: what   did we say")
    assert draft.label == "what did we say about my arms build last week, in detail…"


async def test_offer_exchange_is_a_no_op_without_an_indexer():
    kb_indexer.offer_exchange(ExchangeJob(uuid.uuid4(), uuid.uuid4(), 2, "q", "a", None))  # type: ignore[arg-type]
