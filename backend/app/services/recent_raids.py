"""Welcome-page recent raids: fetch, store and refresh in the background (feature 013).

A refresh has two Warcraft Logs steps (research R1, R2), both in the background lane:

1. **List**: every own character's ``recentReports`` in one aliased request (shared cache
   ``char_reports``, 5 min, so new logs still show up promptly). Reports are merged by code
   across characters.
2. **Details**: only for raid reports that are new or not final yet, from the shared
   ``report_summary`` entries, the uncached ones 10 per request. A report whose log ended
   over 2 h before the fetch is final and never fetched again.

Coordination across instances is the database claim (``repo.claim_refresh``); no DB session
is held across a WCL await.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.cache.cache import CacheFamily, get_many_or_load, keys
from wcl_agent.cache.cache_models import CharacterReports, FightSummary, RecentReport, ReportSummary
from wcl_agent.cache.normalize import FINAL_AFTER
from wcl_agent.game.patch import raid_zone_ids
from wcl_agent.client.queries import character_reports_query
from wcl_agent.tools.report_tools import load_report_summaries, resolve_characters
from wcl_agent.client.wcl_client import background_lane, get_async_client

from ..config import settings
from ..db import repository as repo
from ..db.models import UserCharacter
from ..tenancy.context import RequestIdentity, commit_and_rescope, set_scope, tenant_scope
from . import background
from .recent_raid_types import ListedReport, MplusRun, ReportDetails

logger = logging.getLogger(__name__)

RAID_DIFFICULTIES = frozenset({1, 3, 4, 5})  # LFR, Normal, Heroic, Mythic
DETAIL_BATCH = 10
# Non-raid reports examined for keystone runs per refresh (newest first).
MPLUS_REPORT_BATCH = 10


def character_set_hash(chars: Sequence[UserCharacter]) -> str:
    """Stable hash of the own-character set; a change opens the refresh gate (FR-013)."""
    keys = sorted(f"{c.name}|{c.server}|{c.region}".lower() for c in chars)
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()


def _ms(value: Any) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def _reports_from(node: dict[str, Any] | None) -> CharacterReports | None:
    if node is None:
        return None
    items = ((node.get("recentReports") or {}).get("data")) or []
    return CharacterReports(
        reports=[
            RecentReport(
                code=item["code"],
                title=item.get("title") or item["code"],
                start_time_ms=item["startTime"],
                end_time_ms=item["endTime"],
                zone_id=(item.get("zone") or {}).get("id"),
                zone_name=(item.get("zone") or {}).get("name"),
                guild_name=(item.get("guild") or {}).get("name"),
            )
            for item in items
            if item.get("code") and item.get("startTime") is not None and item.get("endTime") is not None
        ]
    )


async def fetch_listed_reports(
    chars: Sequence[UserCharacter], raid_zones: set[int]
) -> list[ListedReport]:
    """The list step: every own character's recent reports, merged by code.

    Batched (PERF-001): the characters' ids come from one request at most (usually cached),
    and every uncached report list from one more. A WCL failure fails the step unchanged
    (the caller maps it to an error).
    """
    if not chars:
        return []
    refs = await resolve_characters([(c.name, c.server, c.region) for c in chars])
    known = [(c, ref) for c, ref in zip(chars, refs) if ref is not None]
    if not known:
        return []
    limit = settings.recent_raids_limit

    async def load(missing: list[int]) -> list[CharacterReports | None]:
        variables: dict[str, Any] = {f"id{j}": known[i][1].id for j, i in enumerate(missing)}
        variables["limit"] = limit
        data = await get_async_client().query(character_reports_query(len(missing)), variables)
        nodes = ((data.get("data") or {}).get("characterData")) or {}
        return [_reports_from(nodes.get(f"c{j}")) for j in range(len(missing))]

    lists = await get_many_or_load(
        CacheFamily.CHAR_REPORTS,
        [keys.char_reports(ref.id, limit) for _, ref in known],
        CharacterReports,
        load,
    )
    merged: dict[str, ListedReport] = {}
    for (c, _), listed in zip(known, lists):
        for item in listed.reports if listed is not None else []:
            prev = merged.get(item.code)
            if prev is not None:
                merged[item.code] = replace(prev, character_ids=prev.character_ids | {c.id})
                continue
            merged[item.code] = ListedReport(
                code=item.code,
                title=item.title,
                zone_id=item.zone_id,
                zone_name=item.zone_name,
                guild_name=item.guild_name,
                started_at=_ms(item.start_time_ms),
                ended_at=_ms(item.end_time_ms),
                character_ids=frozenset({c.id}),
                is_raid=item.zone_id in raid_zones,
            )
    return list(merged.values())


def _details_from(summary: ReportSummary, raid_zones: set[int]) -> ReportDetails:
    fights = [f for f in summary.fights if f.encounter_id and f.difficulty in RAID_DIFFICULTIES]
    pulled = {f.encounter_id for f in fights}
    killed = {f.encounter_id for f in fights if f.kill is True}
    return ReportDetails(
        ended_at=_ms(summary.end_time_ms),
        difficulty=max((f.difficulty for f in fights if f.difficulty is not None), default=None),
        bosses_pulled=len(pulled),
        bosses_killed=len(killed),
        is_raid=summary.zone_id in raid_zones,
    )


def _fight_characters(
    summary: ReportSummary, fight: FightSummary, own: Mapping[uuid.UUID, str]
) -> frozenset[uuid.UUID]:
    """The own characters among a fight's players, matched by name (actors carry no server).

    Falls back to all of the report's own characters when none match, so a run is never
    left unnamed.
    """
    names = {summary.players[p].name.casefold() for p in fight.player_ids if p in summary.players}
    present = frozenset(cid for cid, name in own.items() if name.casefold() in names)
    return present or frozenset(own)


def extract_mplus_runs(summary: ReportSummary, own: Mapping[uuid.UUID, str]) -> list[MplusRun]:
    """The completed keystone fights of a report (feature 022), each naming its own characters.

    ``own`` maps the report's own characters (id → name). Completed means a kill with a
    keystone level; an abandoned key is dropped. A key finished over the timer (depleted)
    is kept and not timed: ``keystoneBonus`` counts the upgrade chests, so 0 is depleted.
    """
    return [
        MplusRun(
            report_code=summary.code,
            fight_id=f.id,
            dungeon=f.name or summary.zone_name or "Mythic+",
            key_level=f.keystone_level,
            started_at=_ms(summary.start_time_ms + (f.start_time_ms or 0)),
            timed=(f.keystone_bonus or 0) >= 1,
            character_ids=_fight_characters(summary, f, own),
        )
        for f in summary.fights
        if f.keystone_level and f.keystone_level > 0 and f.kill is True
    ]


async def fetch_report_summaries(codes: Sequence[str]) -> dict[str, ReportSummary]:
    """Summaries for up to ``DETAIL_BATCH`` codes: uncached ones in one request.

    A report WCL can't return (deleted, made private) is skipped and stays non-final; it
    fails the batched GraphQL request, so the batch then falls back to one request each.
    An HTTP-level failure fails the step unchanged.
    """
    if not codes:
        return {}
    try:
        summaries = await load_report_summaries(codes)
    except RuntimeError:
        if len(codes) == 1:
            logger.info("recent raids: report %s unavailable, skipped", codes[0])
            return {}
        out: dict[str, ReportSummary] = {}
        for code in codes:
            out.update(await fetch_report_summaries([code]))
        return out
    return {code: summary for code, summary in zip(codes, summaries) if summary is not None}


async def fetch_report_details(
    codes: Sequence[str], raid_zones: set[int]
) -> dict[str, ReportDetails]:
    """The detail step for up to ``DETAIL_BATCH`` codes (see ``fetch_report_summaries``)."""
    summaries = await fetch_report_summaries(codes)
    return {code: _details_from(summary, raid_zones) for code, summary in summaries.items()}


async def _refresh(tenant_id: uuid.UUID, chars: Sequence[UserCharacter], deadline: float) -> None:
    """Both steps share the ``deadline`` (loop time); only the raid step can fail the run.

    The M+ step has its own timeout scope so a WCL error or timeout there is logged and
    leaves the raids, the stored runs and the refresh outcome alone (FR-010).
    """
    async with asyncio.timeout_at(deadline):
        raid_zones = await raid_zone_ids()
        listed = await fetch_listed_reports(chars, raid_zones)
        async with tenant_scope(tenant_id) as session:
            need = set(
                await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=listed)
            )
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
    try:
        async with asyncio.timeout_at(deadline):
            await _refresh_mplus_runs(
                tenant_id, listed, need, raid_zones, {c.id: c.name for c in chars}
            )
    except Exception as exc:  # noqa: BLE001 - a failed M+ step never fails the refresh
        error = _error_code(exc)
        if error == "unknown":
            logger.exception("recent raids: M+ step failed (tenant %s)", tenant_id)
        else:
            logger.warning("recent raids: M+ step failed (tenant %s): %s", tenant_id, error)


async def _refresh_mplus_runs(
    tenant_id: uuid.UUID,
    listed: Sequence[ListedReport],
    need: set[str],
    raid_zones: set[int],
    names: Mapping[uuid.UUID, str],
) -> None:
    """The M+ step (feature 022): keystone runs from the newest non-raid reports still open.

    Same summaries the raid details use, so the shared cache and the raw-fetch write-through
    apply. A non-raid report is marked final like a raid once it ended long ago, so it is not
    examined again; that happens in the transaction that stores its runs, so a report whose
    fetch failed stays open and is examined on the next refresh.
    """
    by_code = {r.code: r for r in listed}
    wanted = sorted(
        (r for r in listed if r.code in need and not r.is_raid),
        key=lambda r: r.started_at,
        reverse=True,
    )[:MPLUS_REPORT_BATCH]
    codes = [r.code for r in wanted]
    for start in range(0, len(codes), DETAIL_BATCH):
        summaries = await fetch_report_summaries(codes[start : start + DETAIL_BATCH])
        final_before = datetime.now(timezone.utc) - FINAL_AFTER
        async with tenant_scope(tenant_id) as session:
            for code, summary in summaries.items():
                await repo.upsert_mplus_runs(
                    session,
                    tenant_id=tenant_id,
                    runs=extract_mplus_runs(
                        summary, {cid: names[cid] for cid in by_code[code].character_ids}
                    ),
                )
                await repo.set_report_details(
                    session,
                    tenant_id=tenant_id,
                    code=code,
                    details=_details_from(summary, raid_zones),
                    final_before=final_before,
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
        deadline = asyncio.get_running_loop().time() + settings.recent_raids_refresh_timeout_s
        with background_lane():
            await _refresh(tenant_id, chars, deadline)
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
