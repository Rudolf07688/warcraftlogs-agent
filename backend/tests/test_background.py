"""``background.spawn`` (sc-222): a spawned task never inherits the caller's context."""

from __future__ import annotations

import asyncio
import uuid

from backend.app.services import background
from backend.app.tenancy.context import RequestIdentity, current_identity


async def test_spawned_task_starts_without_the_callers_identity():
    identity = RequestIdentity(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), membership_role="member",
        is_platform_admin=False, session_id=uuid.uuid4(),
    )
    seen: list = []
    done = asyncio.Event()

    async def job() -> None:
        seen.append(current_identity.get())
        done.set()

    token = current_identity.set(identity)
    try:
        background.spawn(job(), ("test-spawn", uuid.uuid4()))
    finally:
        current_identity.reset(token)
    await asyncio.wait_for(done.wait(), 1)
    assert seen == [None]
