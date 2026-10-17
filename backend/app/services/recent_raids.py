"""Welcome-page recent raids: fetch, store and refresh in the background (feature 013).

A refresh has two Warcraft Logs steps (research R1, R2), both in the background lane:

1. **List**: one aliased ``recentReports`` request for every own character, uncached so new
   logs show up. Reports are merged by code across characters.
2. **Details**: only for raid reports that are new or not final yet, batched 10 per request.
   A report whose log ended over 2 h before the fetch is final and never fetched again.

Coordination across instances is the database claim (``repo.claim_refresh``); no DB session
is held across a WCL await.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.patch import raid_zone_ids
from wcl_agent.queries import recent_reports_query, report_details_query
from wcl_agent.report_tools import _server_slug
from wcl_agent.wcl_client import background_lane, get_async_client

from ..config import settings
from ..db import repository as repo
from ..db.models import UserCharacter
from ..tenancy.context import RequestIdentity, commit_and_rescope, set_scope, tenant_scope
from . import background
from .recent_raid_types import ListedReport, ReportDetails

logger = logging.getLogger(__name__)

RAID_DIFFICULTIES = frozenset({1, 3, 4, 5})  # LFR, Normal, Heroic, Mythic
FINAL_AFTER = timedelta(hours=2)
DETAIL_BATCH = 10


def character_set_hash(chars: Sequence[UserCharacter]) -> str:
    """Stable hash of the own-character set; a change opens the refresh gate (FR-013)."""
    keys = sorted(f"{c.name}|{c.server}|{c.region}".lower() for c in chars)
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()


def _ms(value: Any) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


async def fetch_listed_reports(
    chars: Sequence[UserCharacter], raid_zones: set[int]
) -> list[ListedReport]:
    """The list step: every own character's recent reports in one request, merged by code."""
    if not chars:
        return []
    variables: dict[str, Any] = {"limit": settings.recent_raids_limit}
    for i, c in enumerate(chars):
        variables[f"n{i}"] = c.name
        variables[f"s{i}"] = _server_slug(c.server)
        variables[f"r{i}"] = c.region.upper()
    data = await get_async_client().query(recent_reports_query(len(chars)), variables, cache=False)
    by_alias = ((data.get("data") or {}).get("characterData")) or {}

    merged: dict[str, ListedReport] = {}
    for i, c in enumerate(chars):
        node = by_alias.get(f"c{i}")  # null: character not found on WCL
        items = ((node or {}).get("recentReports") or {}).get("data") or []
        for item in items:
            code = item.get("code")
            if not code or item.get("startTime") is None or item.get("endTime") is None:
                continue
            prev = merged.get(code)
            if prev is not None:
                merged[code] = replace(prev, character_ids=prev.character_ids | {c.id})
                continue
            zone = item.get("zone") or {}
            zone_id = zone.get("id")
            merged[code] = ListedReport(
                code=code,
                title=item.get("title") or code,
                zone_id=zone_id,
                zone_name=zone.get("name"),
                guild_name=(item.get("guild") or {}).get("name"),
                started_at=_ms(item["startTime"]),
                ended_at=_ms(item["endTime"]),
                character_ids=frozenset({c.id}),
                is_raid=zone_id in raid_zones,
            )
    return list(merged.values())


def _details_from(report: dict[str, Any], raid_zones: set[int]) -> ReportDetails:
    fights = [
        f
        for f in report.get("fights") or []
        if f.get("encounterID") and f.get("difficulty") in RAID_DIFFICULTIES
    ]
    pulled = {f["encounterID"] for f in fights}
    killed = {f["encounterID"] for f in fights if f.get("kill") is True}
    zone_id = (report.get("zone") or {}).get("id")
    return ReportDetails(
        ended_at=_ms(report["endTime"]),
        difficulty=max((f["difficulty"] for f in fights), default=None),
        bosses_pulled=len(pulled),
        bosses_killed=len(killed),
        is_raid=zone_id in raid_zones,
    )


async def fetch_report_details(
    codes: Sequence[str], raid_zones: set[int]
) -> dict[str, ReportDetails]:
    """The detail step for up to ``DETAIL_BATCH`` codes in one (cached) request.

    A report WCL can't return (deleted, made private) is skipped and stays non-final.
    """
    if not codes:
        return {}
    variables = {f"c{i}": code for i, code in enumerate(codes)}
    try:
        data = await get_async_client().query(report_details_query(len(codes)), variables)
    except RuntimeError:
        if len(codes) == 1:
            logger.info("recent raids: report %s unavailable, skipped", codes[0])
            return {}
        # One bad report fails the whole batch's GraphQL: fall back to one request each.
        out: dict[str, ReportDetails] = {}
        for code in codes:
            out.update(await fetch_report_details([code], raid_zones))
        return out
    reports = ((data.get("data") or {}).get("reportData")) or {}
    out = {}
    for i, code in enumerate(codes):
        report = reports.get(f"r{i}")
        if report and report.get("endTime") is not None:
            out[code] = _details_from(report, raid_zones)
    return out


async def _refresh(tenant_id: uuid.UUID, chars: Sequence[UserCharacter]) -> None:
    raid_zones = await raid_zone_ids()
    listed = await fetch_listed_reports(chars, raid_zones)
    async with tenant_scope(tenant_id) as session:
        need = set(await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=listed))
    # Details only matter for raids the welcome list can show: the newest ones.
    wanted = sorted(
        (r for r in listed if r.code in need and r.is_raid),
        key=lambda r: r.started_at,
        reverse=True,
    )[: settings.recent_raids_limit]
    codes = [r.code for r in wanted]
    for start in range(0, len(codes), DETAIL_BATCH):
        details = await fetch_report_details(codes[start : start + DETAIL_BATCH], raid_zones)
        final_before = datetime.now(timezone.utc) - FINAL_AFTER
        async with tenant_scope(tenant_id) as session:
            for code, d in details.items():
                await repo.set_report_details(
                    session, tenant_id=tenant_id, code=code, details=d, final_before=final_before
                )


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "rate_limited" if exc.response.status_code == 429 else "wcl_unavailable"
    if isinstance(exc, httpx.HTTPError):
        return "wcl_unavailable"
    return "unknown"


async def run_recent_raid_refresh(tenant_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """One claimed refresh run; always records its outcome against ``run_id``."""
    ok, error = False, "unknown"
    try:
        async with tenant_scope(tenant_id) as session:
            chars = await repo.list_own_characters(session, tenant_id=tenant_id)
        with background_lane():
            async with asyncio.timeout(settings.recent_raids_refresh_timeout_s):
                await _refresh(tenant_id, chars)
        ok, error = True, None
    except Exception as exc:  # noqa: BLE001 - mapped to a short user-safe code
        error = _error_code(exc)
        if error == "unknown":
            logger.exception("recent raids refresh failed (tenant %s)", tenant_id)
        else:
            logger.warning("recent raids refresh failed (tenant %s): %s", tenant_id, error)
    finally:
        try:
            async with tenant_scope(tenant_id) as session:
                await repo.finish_refresh(
                    session, tenant_id=tenant_id, run_id=run_id, ok=ok, error=error
                )
        except Exception:  # noqa: BLE001 - the stale reclaim recovers a lost outcome
            logger.exception("recent raids: could not record the refresh outcome")


async def maybe_start_refresh(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    chars: Sequence[UserCharacter],
    force: bool = False,
    identity: RequestIdentity | None = None,
) -> bool:
    """Claim and schedule a refresh when due; ``True`` when this call started one.

    Commits the claim before scheduling so other instances see it, then re-applies the
    tenant scope so the caller can keep using ``session``.
    """
    run_id = await repo.claim_refresh(
        session,
        tenant_id=tenant_id,
        character_set=character_set_hash(chars),
        force=force,
        min_gap_s=settings.recent_raids_refresh_min_s,
        stale_s=settings.recent_raids_stale_s,
    )
    if run_id is None:
        return False
    if identity is not None:
        await commit_and_rescope(session, identity)
    else:
        await session.commit()
        await set_scope(session, tenant_id=tenant_id)
    # Keyed by run: a reclaimed run must start even if a stale one lingers in this process.
    background.spawn(run_recent_raid_refresh(tenant_id, run_id), ("recent_raids", run_id))
    return True
