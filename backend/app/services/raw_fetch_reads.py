"""DB-first reads (feature 039, sc-129): the WCL client's fetch source.

Installed by the app lifespan with :func:`wcl_agent.client.wcl_client.set_fetch_source`. The
client asks it before every network call, in the caller's own context, so the order is the
callers' Redis ``get_or_load`` → this store → Warcraft Logs, and a store hit back-fills Redis
through the unchanged loaders. Visibility is the repository's one read function; this module
adds the tenant, the freshness rule and the fail-open bounds (research R5/R6).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from wcl_agent.cache.cache import unfinished_ttl
from wcl_agent.cache.normalize import is_finished
from wcl_agent.client.wcl_client import exact_report_codes, operation_name

from ..config import settings
from ..db import session as db_session
from ..repositories.raw_fetches import ReportStatus, read_visible_fetch
from ..tenancy.context import current_identity, set_scope

logger = logging.getLogger(__name__)

READ_TIMEOUT_S = 3.0  # a slow store costs at most this, then the query goes to WCL


def is_fresh(fetched_at: datetime, statuses: list[ReportStatus | None], *, now: datetime) -> bool:
    """Research R6. Report data is kept for good once every report was seen finished and the
    row was fetched after it finished; otherwise only while younger than the live window
    (``WCL_CACHE_UNFINISHED_TTL``, the Redis rule for reports still being logged). Rows naming
    no report (rankings, characters, world data) are never served: Redis TTLs govern them."""
    if not statuses:
        return False
    if now - fetched_at < timedelta(seconds=unfinished_ttl()):
        return True
    return all(
        s is not None
        and s.end_time_ms is not None
        and is_finished(s.end_time_ms, now=s.checked_at)
        and is_finished(s.end_time_ms, now=fetched_at)
        for s in statuses
    )


async def read_stored_fetch(query_key: str, query: str, variables: dict[str, Any]) -> bytes | None:
    """The stored body the current turn's tenant may be served for this query, or None."""
    if not exact_report_codes(query, variables):
        return None  # non-report data, or a query naming reports we can't fully parse
    identity = current_identity.get()
    tenant_id = identity.tenant_id if identity is not None else None  # None: public only
    now = datetime.now(UTC)
    since = now - timedelta(days=settings.raw_store_reverify_days)
    try:
        async with asyncio.timeout(READ_TIMEOUT_S), db_session.SessionLocal() as session:
            await set_scope(session, tenant_id=tenant_id)
            body = await read_visible_fetch(
                session, query_key, tenant_id=tenant_id, since=since, fresh=partial(is_fresh, now=now)
            )
    except Exception as exc:  # noqa: BLE001 - a turn never fails because of the store (FR-015)
        logger.debug("raw store read failed: %s", type(exc).__name__)
        return None
    if body is None:
        return None
    logger.info("wcl store hit op=%s", operation_name(query) or "anonymous")
    return body.encode()
