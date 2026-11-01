"""A card click during the answer's save neither deadlocks nor loses the answer (047 P7 SEC-005).

Cancel/approve lock the card, then save their line (add_message locks the conversation, sc-255).
The chat socket's final save takes the same order: the turn's cards first, then the conversation.
Real Postgres only (row locks); skipped otherwise, like test_proposal_race_pg.py.
"""

from __future__ import annotations

import asyncio

import sqlalchemy as sa

from backend.app.api import proposals as routes
from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.db.models import Message
from backend.app.tenancy.context import tenant_scope
from backend.tests.test_proposal_race_pg import me, pg, proposal, pytestmark  # noqa: F401 - fixtures


async def test_a_cancel_during_the_final_save_waits_and_both_are_saved(me, proposal, monkeypatch):  # noqa: F811
    real = repo.add_message

    async def slow_follow_up(session, conv_id, role, content, *args, **kwargs):
        if content != "the answer":
            await asyncio.sleep(0.3)  # the cancel holds the card's lock while it saves its line
        return await real(session, conv_id, role, content, *args, **kwargs)

    monkeypatch.setattr(repo, "add_message", slow_follow_up)
    cancel = asyncio.create_task(routes.cancel(proposal.id, me))
    await asyncio.sleep(0.1)  # the card is locked
    _, seq = await asyncio.wait_for(
        ws_mod._save_answer(me, proposal.conversation_id, "the answer", [proposal.id]), 10
    )
    decided = await cancel

    assert decided.proposal.status == "cancelled" and decided.follow_up is not None
    async with tenant_scope(me.tenant_id, user_id=me.user_id) as db:
        lines = list(await db.execute(
            sa.select(Message.seq, Message.content)
            .where(Message.conversation_id == proposal.conversation_id)
            .order_by(Message.seq)
        ))
    assert [content for _, content in lines] == ["Cancelled. Your profile is unchanged.", "the answer"]
    assert seq == lines[-1][0]
