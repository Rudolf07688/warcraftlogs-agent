"""Recent-raid kickoff pre-fetch (046, sc-339).

Clicking a recent raid (``POST /api/raids/{code}/investigate``) starts this in the background,
so the kickoff turn's tool calls are answered locally instead of rediscovering the report: the
report summary (``get_report_fights``'s data) and one ``Summary`` table per boss, the sequence
the agent instruction's RECENT_RAID_KICKOFF playbook names, for the fights of the tool's
``bosses`` list. It calls the agent tools' own loaders, so every query is byte for byte the one
the turn sends (the tables raw, without the tool's compaction: QA PERF-003): the turn hits the
Redis cache, the raw store (039) or this job's single-flight.

Rules:

* It runs only after the endpoint's 404 rule passed: the report is the workspace's own recent
  or tracked raid.
* It acts as the clicking user's workspace (``current_identity``), so the fetch sink grants
  the report to that workspace exactly as its own chat turn would, and the store answers only
  what that workspace may see (the 039 rule). It is no chat turn: there is no refresh actor
  (it never forces a refresh) and no turn to count.
* At most 1 + :data:`MAX_BOSS_TABLES` Warcraft Logs requests; it never delays the response, and
  a failure is only logged. The boss tables run in the background lane (at most
  ``WCL_BACKGROUND_CONCURRENCY`` at once, yielding to chat turns); a chat turn that joins one of
  them in flight promotes it to the interactive lane (048). The summary is the kickoff turn's
  own first call and is shared through the cache's single-flight, which a joiner can't promote,
  so it is loaded in the interactive lane: the turn never waits on a background slot for it.
* One job per (workspace, report) per :data:`COOLDOWN_S`: a repeat click within it starts
  nothing (P7-046 SEC-001). The cooldown is in-process: each app instance keeps its own.
* Only when store reads are on and the store is installed as the client's fetch source: without
  them a whole-raid table is not kept anywhere the turn could read (SEC-002). Not while the
  store's breaker is open or the workspace is skipping the store either: the job would warm
  nothing (052 sc-352, QA BUG-003).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from wcl_agent.cache.cache_models import ReportSummary
from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import background_lane
from wcl_agent.tools.report_tools import boss_summary, load_report_summary, load_report_table

from ..config import settings
from ..tenancy.context import RequestIdentity, current_identity
from . import background, raw_fetch_reads

logger = logging.getLogger(__name__)

MAX_BOSS_TABLES = 10
BOSS_TABLE = "Summary"
COOLDOWN_S = 600.0
# (workspace, report) -> when its last job started (monotonic); entries older than the cooldown
# are dropped on the next schedule, so this holds at most the clicks of one cooldown window.
_started: dict[tuple[uuid.UUID | None, str], float] = {}


def pick_boss_fights(summary: ReportSummary) -> list[int]:
    """The fights the kickoff turn asks for: one per entry of ``get_report_fights``'s
    ``bosses`` (Mythic+ key runs are no bosses), its last kill, else its last pull, in
    first-pull order (QA BUG-001)."""
    return [
        boss["last_kill_fight_id"] or boss["last_pull_fight_id"] for boss in boss_summary(summary)
    ][:MAX_BOSS_TABLES]


async def prefetch(identity: RequestIdentity, report_code: str) -> None:
    """Warm the report summary and its per-boss Summary tables as ``identity``'s workspace."""
    current_identity.set(identity)  # a fresh context (background.spawn): this task only
    try:
        summary = await load_report_summary(report_code)
        if summary is None:
            return
        fights = pick_boss_fights(summary)
        with background_lane():  # raw tables only: warming needs no compaction (QA PERF-003)
            results = await asyncio.gather(
                *(load_report_table(report_code, BOSS_TABLE, fight_id) for fight_id in fights),
                return_exceptions=True,
            )
    except Exception as exc:  # noqa: BLE001 - a warm-up; the turn fetches what it lacks
        logger.warning("kickoff prefetch failed report=%s error=%s", report_code, type(exc).__name__)
        return
    failed = sum(1 for r in results if r is None or isinstance(r, BaseException))
    logger.info("kickoff prefetch report=%s tables=%d failed=%d", report_code, len(fights), failed)


def store_reads_on() -> bool:
    """The turn can read what the pre-fetch fetched: store reads on and the store installed."""
    return settings.wcl_store_reads_enabled and wcl_client._fetch_source is not None


def schedule(identity: RequestIdentity, report_code: str) -> bool:
    """Start :func:`prefetch` unless store reads are off, the store skips this workspace (breaker
    open, or its own timeouts), or this workspace started one for the report less than
    :data:`COOLDOWN_S` ago; True when it started."""
    if not store_reads_on() or raw_fetch_reads.breaker.skips(identity.tenant_id):
        return False
    now = time.monotonic()
    for key, at in list(_started.items()):
        if now - at >= COOLDOWN_S:
            del _started[key]
    key = (identity.tenant_id, report_code)
    if key in _started:
        return False
    _started[key] = now
    background.spawn(prefetch(identity, report_code), ("kickoff_prefetch", *key))
    return True
