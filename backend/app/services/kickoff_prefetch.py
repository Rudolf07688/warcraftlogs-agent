"""Recent-raid kickoff pre-fetch (046, sc-339).

Clicking a recent raid (``POST /api/raids/{code}/investigate``) starts this in the background,
so the kickoff turn's tool calls are answered locally instead of rediscovering the report: the
report summary (``get_report_fights``'s data) and one ``Summary`` table per boss, the sequence
the agent instruction's RECENT_RAID_KICKOFF playbook names. It calls the agent's own tool
functions, so every query is byte for byte the one the turn sends: the turn hits the Redis
cache, the raw store (039) or this job's single-flight.

Rules:

* It runs only after the endpoint's 404 rule passed: the report is the workspace's own recent
  or tracked raid.
* It acts as the clicking user's workspace (``current_identity``), so the fetch sink grants
  the report to that workspace exactly as its own chat turn would, and the store answers only
  what that workspace may see (the 039 rule). It is no chat turn: there is no refresh actor
  (it never forces a refresh) and no turn to count.
* At most 1 + :data:`MAX_BOSS_TABLES` Warcraft Logs requests, in the background lane (at most
  ``WCL_BACKGROUND_CONCURRENCY`` at once, yielding to chat turns); it never delays the response,
  and a failure is only logged.
* One job per (workspace, report) per :data:`COOLDOWN_S`: a repeat click within it starts
  nothing (P7-046 SEC-001). The cooldown is in-process: each app instance keeps its own.
* Only when store reads are on and the store is installed as the client's fetch source: without
  them a whole-raid table is not kept anywhere the turn could read (SEC-002).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from wcl_agent.cache.cache_models import ReportSummary
from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import background_lane
from wcl_agent.tools.report_tools import get_report_table, load_report_summary

from ..config import settings
from ..tenancy.context import RequestIdentity, current_identity
from . import background

logger = logging.getLogger(__name__)

MAX_BOSS_TABLES = 10
BOSS_TABLE = "Summary"
COOLDOWN_S = 600.0
# (workspace, report) -> when its last job started (monotonic); entries older than the cooldown
# are dropped on the next schedule, so this holds at most the clicks of one cooldown window.
_started: dict[tuple[uuid.UUID | None, str], float] = {}


def pick_boss_fights(summary: ReportSummary) -> list[int]:
    """One fight per boss and difficulty, in first-pull order: the last kill, else the last pull."""
    chosen: dict[tuple[int, int | None], tuple[bool, int]] = {}
    for fight in summary.fights:
        if not fight.encounter_id:
            continue  # trash
        key = (fight.encounter_id, fight.difficulty)
        previous = chosen.get(key)
        if fight.kill or previous is None or not previous[0]:
            chosen[key] = (bool(fight.kill), fight.id)
    return [fight_id for _, fight_id in chosen.values()][:MAX_BOSS_TABLES]


async def prefetch(identity: RequestIdentity, report_code: str) -> None:
    """Warm the report summary and its per-boss Summary tables as ``identity``'s workspace."""
    current_identity.set(identity)  # a fresh context (background.spawn): this task only
    try:
        with background_lane():
            summary = await load_report_summary(report_code)
            if summary is None:
                return
            fights = pick_boss_fights(summary)
            results = await asyncio.gather(
                *(get_report_table(report_code, BOSS_TABLE, fight_id=fight_id) for fight_id in fights)
            )
    except Exception as exc:  # noqa: BLE001 - a warm-up; the turn fetches what it lacks
        logger.warning("kickoff prefetch failed report=%s error=%s", report_code, type(exc).__name__)
        return
    failed = sum(1 for r in results if r.get("status") != "success")
    logger.info("kickoff prefetch report=%s tables=%d failed=%d", report_code, len(fights), failed)


def store_reads_on() -> bool:
    """The turn can read what the pre-fetch fetched: store reads on and the store installed."""
    return settings.wcl_store_reads_enabled and wcl_client._fetch_source is not None


def schedule(identity: RequestIdentity, report_code: str) -> bool:
    """Start :func:`prefetch` unless store reads are off or this workspace started one for the
    report less than :data:`COOLDOWN_S` ago; True when it started."""
    if not store_reads_on():
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
