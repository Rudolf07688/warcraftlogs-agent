"""US2 tests: message status/partial persistence + durable ADK sessions.

The session-restore test uses a file-backed SQLite DB so a *fresh* engine (a
simulated process restart) reads rows written by the previous one — proving the
DatabaseSessionService restores context, not just the displayed transcript.
"""

from __future__ import annotations

import uuid

import pytest
from google.adk.events import Event
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.api import ws as ws_module
from backend.app.db import repository as repo
from backend.app.db.models import Base

APP_NAME = "wcl_app"
USER_ID = "local_user"


async def test_add_message_status_default_and_partial(session):
    conv = await repo.create_conversation(session, model="gemini-3.6-flash")
    done = await repo.add_message(session, conv.id, "agent", "finished")
    part = await repo.add_message(session, conv.id, "agent", "half…", status="partial")
    assert done.status == "complete"
    assert part.status == "partial"


async def test_persist_partial_writes_partial_message(session):
    conv = await repo.create_conversation(session, model="gemini-3.6-flash")
    await session.commit()
    await ws_module._persist_partial(session, conv.id, ["chunk one ", "chunk two"])
    msgs = await repo.list_messages(session, conv.id)
    assert len(msgs) == 1
    assert msgs[0].role == "agent"
    assert msgs[0].status == "partial"
    assert msgs[0].content == "chunk one chunk two"


async def test_persist_partial_noop_when_empty(session):
    conv = await repo.create_conversation(session, model="gemini-3.6-flash")
    await session.commit()
    await ws_module._persist_partial(session, conv.id, [])
    assert (await repo.list_messages(session, conv.id)) == []


async def test_adk_session_context_survives_restart(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"
    session_id = str(uuid.uuid4())
    user_text = "remember: the raid wiped on Mythic Gnarlroot"

    # --- First "process": write a session + a turn, then shut down the engine. ---
    engine1 = create_async_engine(db_url)
    async with engine1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    svc1 = DatabaseSessionService(db_engine=engine1)
    await svc1.prepare_tables()
    sess = await svc1.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id, state={})
    await svc1.append_event(
        sess,
        Event(author="user", content=types.Content(role="user", parts=[types.Part(text=user_text)])),
    )
    await engine1.dispose()

    # --- Second "process": a brand-new engine must restore the prior context. ---
    engine2 = create_async_engine(db_url)
    svc2 = DatabaseSessionService(db_engine=engine2)
    await svc2.prepare_tables()
    restored = await svc2.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    assert restored is not None
    texts = [
        p.text
        for e in restored.events
        if e.content and e.content.parts
        for p in e.content.parts
        if p.text
    ]
    assert any(user_text in t for t in texts)
    await engine2.dispose()
