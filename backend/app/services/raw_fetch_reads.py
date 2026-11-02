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
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from wcl_agent.cache.cache import current_turn, record_store, unfinished_ttl
from wcl_agent.cache.normalize import is_finished
from wcl_agent.client.wcl_client import StoredFetch, exact_report_codes, operation_name

from ..config import settings
from ..db import session as db_session
from ..repositories.raw_fetches import ReportStatus, probe_visible_fetch
from ..tenancy.context import current_identity

logger = logging.getLogger(__name__)

BREAKER_S = 30.0  # once open, no probe for this long
# 052 sc-355: timeouts open it only from two turns or more inside the window, and only while
# they are at least half the window's probes; a turn with this many skips the store itself.
TIMEOUTS_TO_OPEN = 3
WINDOW_S = 60.0
_WINDOW_MAX = 256  # probe outcomes kept; older ones fall out of the ratio early

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

    Closed (``open_until`` 0): every call probes, except a turn that already had
    :data:`TIMEOUTS_TO_OPEN` timeouts inside the window (its own cap, 052 sc-355). A connection
    error opens it for :data:`BREAKER_S` at once: no probe at all. Timeouts (a slow read or a
    wait for a pool connection) open it when the last :data:`WINDOW_S` hold at least
    :data:`TIMEOUTS_TO_OPEN` of them, from two turns or more, and they are at least half of the
    window's probes: one turn's burst of parallel probes alone never does, and a store slow for
    most reads does even when one answers in between. Reads outside a chat turn (``turn``
    None: the kickoff pre-fetch, background jobs) count as one turn. After the wait it is
    half-open: one call probes (the trial) while the others skip; the trial's success closes
    it, its failure (a timeout too) opens it again, and a trial that ends otherwise
    (cancelled, another error) frees the trial for the next.
    """

    open_until: float = 0.0
    trial: bool = False
    # (when, turn, timed out) per finished probe while closed, oldest first
    recent: deque[tuple[float, object | None, bool]] = field(
        default_factory=lambda: deque(maxlen=_WINDOW_MAX), repr=False
    )
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def is_open(self) -> bool:
        """Whether no probe may run now (open and still waiting). Changes nothing (sc-352)."""
        return bool(self.open_until) and self.clock() < self.open_until

    def admit(self, turn: object | None = None) -> bool | None:
        """None: skip the store. Otherwise probe; True when this probe is the trial."""
        if not self.open_until:
            timeouts = sum(1 for _, t, out in self._window() if out and t is turn)
            return None if timeouts >= TIMEOUTS_TO_OPEN else False
        if self.clock() < self.open_until or self.trial:
            return None
        self.trial = True
        return True

    def succeeded(self, trial: bool, turn: object | None = None) -> None:
        if trial:
            self.open_until, self.trial = 0.0, False
        else:
            self.recent.append((self.clock(), turn, False))

    def timed_out(self, trial: bool, turn: object | None = None) -> None:
        """One probe timed out: opens on the window rule, or at once for the half-open trial
        (the store was just failing)."""
        if trial:
            self.failed()
            return
        self.recent.append((self.clock(), turn, True))
        window = self._window()
        timeouts = [t for _, t, out in window if out]
        if (
            len(timeouts) >= TIMEOUTS_TO_OPEN
            and 2 * len(timeouts) >= len(window)
            and any(t is not timeouts[0] for t in timeouts)
        ):
            self.failed()

    def failed(self) -> None:
        if not self.open_until:
            logger.warning("raw store unavailable, skipping it for %.0fs", BREAKER_S)
        self.open_until, self.trial = self.clock() + BREAKER_S, False
        self.recent.clear()

    def released(self, trial: bool) -> None:
        if trial:
            self.trial = False

    def _window(self) -> deque[tuple[float, object | None, bool]]:
        """:attr:`recent` without the outcomes older than :data:`WINDOW_S`."""
        since = self.clock() - WINDOW_S
        while self.recent and self.recent[0][0] <= since:
            self.recent.popleft()
        return self.recent


breaker = Breaker()


def _is_timeout(exc: BaseException) -> bool:
    """The probe's own timeout or the pool's wait for a connection: the store may only be slow."""
    return isinstance(exc, TimeoutError | PoolTimeout)


def _is_outage(exc: BaseException) -> bool:
    """A connection-class failure, as opposed to a slow read, a bug or a bad row. Checked after
    :func:`_is_timeout` (``TimeoutError`` is an ``OSError``)."""
    if isinstance(exc, OSError | OperationalError | InterfaceError):
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
        turn = current_turn()
        trial = breaker.admit(turn)
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
            if _is_timeout(exc):
                breaker.timed_out(trial, turn)
                record_store("timeout")
            elif _is_outage(exc):
                breaker.failed()
                record_store("timeout")
            else:
                breaker.released(trial)
                record_store("miss")
            logger.debug("raw store read failed: %s", type(exc).__name__)
            return None
        breaker.succeeded(trial, turn)
        record_store(probe.outcome)
        if probe.body is None:
            return None
        logger.info("wcl store hit op=%s", operation_name(query) or "anonymous")
        return StoredFetch(probe.body, probe.shared)


read_stored_fetch = StoreSource()
