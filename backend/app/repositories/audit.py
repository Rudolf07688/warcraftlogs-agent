"""Append-only auth audit writer (feature 006, FR-030).

Records the security-event set with **non-secret ids only**. ``metadata`` is defensively
run through the redaction helper so a careless caller cannot persist a secret.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.redaction import redact
from ..db.models import AuthAuditEvent


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    outcome: str = "success",
    actor_user_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    event = AuthAuditEvent(
        event_type=event_type,
        outcome=outcome,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        tenant_id=tenant_id,
        request_id=request_id,
        event_metadata=redact(metadata or {}),
    )
    session.add(event)
    await session.flush()
