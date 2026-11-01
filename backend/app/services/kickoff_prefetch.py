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
* At most 1 + :data:`MAX_BOSS_TABLES` Warcraft Logs requests; one job per (workspace, report)
  at a time (``background.spawn``); it never delays the response, and a failure is only logged.
"""

from __future__ import annotations

import asyncio
import logging

from wcl_agent.cache.cache_models import ReportSummary
from wcl_agent.tools.report_tools import get_report_table, load_report_summary

from ..tenancy.context import RequestIdentity, current_identity
from . import background

logger = logging.getLogger(__name__)

MAX_BOSS_TABLES = 10
BOSS_TABLE = "Summary"


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


def schedule(identity: RequestIdentity, report_code: str) -> None:
    """Start :func:`prefetch` unless the same workspace's job for this report is running."""
    background.spawn(prefetch(identity, report_code), ("kickoff_prefetch", identity.tenant_id, report_code))
