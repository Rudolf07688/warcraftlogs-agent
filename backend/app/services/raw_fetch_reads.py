"""DB-first reads (feature 039, sc-129; feature 045, sc-295): the WCL client's fetch source.

Installed by the app lifespan with :func:`wcl_agent.client.wcl_client.set_fetch_source`. The
client asks it once per single-flight, inside a lane slot, before any network call, so the
order is the callers' Redis ``get_or_load`` → this store → Warcraft Logs; a store hit back-fills
Redis through the unchanged loaders unless it isn't public (045 sc-296). Visibility is the
repository's one rule; this module adds the tenant, the freshness rule, the fail-fast bounds
(a short timeout and a breaker, 045 PERF-001) and the probe counters (045 sc-132).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from wcl_agent.cache.cache import record_store, unfinished_ttl
from wcl_agent.cache.normalize import is_finished
from wcl_agent.client.wcl_client import StoredFetch, exact_report_codes, operation_name

from ..config import settings
from ..db import session as db_session
from ..repositories.raw_fetches import ReportStatus, probe_visible_fetch
from ..tenancy.context import current_identity

logger = logging.getLogger(__name__)

BREAKER_S = 30.0  # after a timeout or connection error, no probe for this long


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


@dataclass
class Breaker:
    """Keeps a failing store out of the hot path (045 PERF-001). Process-wide.

    Closed (``open_until`` 0): every call probes. A timeout or connection error opens it for
    :data:`BREAKER_S`: no probe at all. After that it is half-open: one call probes (the
    trial) while the others skip; the trial's success closes it, its failure opens it again,
    and a trial that ends otherwise (cancelled, another error) frees the trial for the next.
    """

    open_until: float = 0.0
    trial: bool = False
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def admit(self) -> bool | None:
        """None: skip the store. Otherwise probe; True when this probe is the trial."""
        if not self.open_until:
            return False
        if self.clock() < self.open_until or self.trial:
            return None
        self.trial = True
        return True

    def succeeded(self, trial: bool) -> None:
        if trial:
            self.open_until, self.trial = 0.0, False

    def failed(self) -> None:
        if not self.open_until:
            logger.warning("raw store unavailable, skipping it for %.0fs", BREAKER_S)
        self.open_until, self.trial = self.clock() + BREAKER_S, False

    def released(self, trial: bool) -> None:
        if trial:
            self.trial = False


breaker = Breaker()


def _is_outage(exc: BaseException) -> bool:
    """A timeout or a connection-class failure, as opposed to a bug or a bad row."""
    if isinstance(exc, TimeoutError | OSError | PoolTimeout | OperationalError | InterfaceError):
        return True
    return isinstance(exc, DBAPIError) and exc.connection_invalidated


class StoreSource:
    """The client's fetch source (045 contracts/fetch-source.md): a callable with a scope."""

    def scope(self) -> str:
        identity = current_identity.get()
        return str(identity.tenant_id) if identity is not None and identity.tenant_id else ""

    async def __call__(self, query_key: str, query: str, variables: dict[str, Any]) -> StoredFetch | None:
        """The stored body the current turn's tenant may be served for this query, or None."""
        if not exact_report_codes(query, variables):
            return None  # non-report data, or a query naming reports we can't fully parse
        trial = breaker.admit()
        if trial is None:
            return None
        identity = current_identity.get()
        tenant_id = identity.tenant_id if identity is not None else None  # None: public only
        now = datetime.now(UTC)
        since = now - timedelta(days=settings.raw_store_reverify_days)
        try:
            async with (
                asyncio.timeout(settings.raw_store_probe_timeout_ms / 1000),
                db_session.SessionLocal() as session,
            ):
                probe = await probe_visible_fetch(
                    session, query_key, tenant_id=tenant_id, since=since, fresh=partial(is_fresh, now=now)
                )
        except asyncio.CancelledError:
            breaker.released(trial)
            raise
        except Exception as exc:  # noqa: BLE001 - a turn never fails because of the store (FR-015)
            if _is_outage(exc):
                breaker.failed()
                record_store("timeout")
            else:
                breaker.released(trial)
                record_store("miss")
            logger.debug("raw store read failed: %s", type(exc).__name__)
            return None
        breaker.succeeded(trial)
        record_store(probe.outcome)
        if probe.body is None:
            return None
        logger.info("wcl store hit op=%s", operation_name(query) or "anonymous")
        return StoredFetch(probe.body, probe.shared)


read_stored_fetch = StoreSource()
