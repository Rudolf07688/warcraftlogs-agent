"""Raid tracking (US1): turn successful report retrievals into TrackedRaid rows.

Fed by the agent-runner backbone (see agent_runner.stream_response): every tool
record is offered here; when a *report-scoped* tool returns successfully for a
``report_code``, we upsert a TrackedRaid. The report label is resolved lazily
(one extra GraphQL call) only the first time a raid is seen, so re-references are
cheap. A successful ``get_report_fights`` already carries the label fields, so that
tool never needs the extra call (PERF-016).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.report_tools import get_report_metadata

from ..db import repository as repo
from ..db.models import TrackedRaid
from .encounters import encounters_from_tool

# Tools whose first positional arg is a real, accessible ``report_code``. A
# successful response from any of these means the log exists and we pulled it.
REPORT_SCOPED_TOOLS = frozenset(
    {
        "get_report_fights",
        "get_report_table",
        "get_report_events",
        "get_report_graph",
        "get_report_rankings",
        "get_report_player_details",
        "get_report_master_data",
    }
)


def _build_label(report_code: str, meta: dict) -> tuple[str, str | None, str | None, datetime | None]:
    """Build ``"<guild> — <zone> — <date>"`` from report metadata, with fallbacks."""
    if meta.get("status") != "success":
        return report_code, None, None, None
    zone = meta.get("zone")
    guild = meta.get("guild")
    ms = meta.get("start_time_ms")
    started = (
        datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        if isinstance(ms, (int, float)) and ms
        else None
    )
    date_str = started.strftime("%Y-%m-%d") if started else None
    parts = [p for p in (guild, zone, date_str) if p]
    label = " — ".join(parts) if parts else (meta.get("title") or report_code)
    return label, zone, guild, started


def _metadata_from_fights(result: dict) -> dict:
    """The label fields of a successful ``get_report_fights`` result, in metadata shape."""
    zone = result.get("zone")
    return {
        "status": "success",
        "title": result.get("title"),
        "zone": zone.get("name") if isinstance(zone, dict) else zone,
        "guild": result.get("guild"),
        "start_time_ms": result.get("start_time_ms"),
    }


async def capture_raid_from_tool(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    ok: bool,
    args: dict,
    conversation_id: uuid.UUID | None,
    result: dict | None = None,
) -> TrackedRaid | None:
    """Upsert a TrackedRaid if this tool record is a successful report retrieval.

    Returns the raid, or ``None`` when the record isn't a successful report-scoped call.
    A successful ``get_report_fights`` also contributes its distinct boss list (US2),
    merged into the raid without duplicating. See ``capture_raid`` for the newness flag.
    """
    raid, _ = await capture_raid(
        session,
        tenant_id=tenant_id,
        name=name,
        ok=ok,
        args=args,
        conversation_id=conversation_id,
        result=result,
    )
    return raid


async def capture_raid(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    ok: bool,
    args: dict,
    conversation_id: uuid.UUID | None,
    result: dict | None = None,
) -> tuple[TrackedRaid | None, bool]:
    """Like ``capture_raid_from_tool``, plus whether the raid was newly tracked.

    The WebSocket layer only announces new raids (PERF-013); a re-referenced raid just
    has its recency touched, which the client picks up on its ``done`` refresh.
    """
    if not ok or name not in REPORT_SCOPED_TOOLS:
        return None, False
    report_code = (args or {}).get("report_code")
    if not report_code or not isinstance(report_code, str):
        return None, False

    # Distinct bosses only come from get_report_fights; [] for every other tool.
    encounters = encounters_from_tool(name, ok, result or {})

    existing = await repo.get_tracked_raid(session, report_code, tenant_id=tenant_id)
    if existing is not None:
        # Known raid — touch recency and merge any new encounters (no extra WCL call).
        raid = await repo.upsert_tracked_raid(
            session,
            tenant_id=tenant_id,
            report_code=report_code,
            label=existing.label,
            conversation_id=conversation_id,
            encounters=encounters,
        )
        return raid, False

    # First time we've seen this report — label it from the fights result when we have
    # one, otherwise resolve its metadata off the event loop.
    if name == "get_report_fights" and (result or {}).get("status") == "success":
        meta = _metadata_from_fights(result or {})
    else:
        try:
            meta = await asyncio.to_thread(get_report_metadata, report_code)
        except Exception:  # noqa: BLE001 - metadata is best-effort; fall back to the code
            meta = {"status": "error"}
    label, zone, guild, started = _build_label(report_code, meta)
    raid = await repo.upsert_tracked_raid(
        session,
        tenant_id=tenant_id,
        report_code=report_code,
        label=label,
        zone=zone,
        guild=guild,
        report_started_at=started,
        conversation_id=conversation_id,
        encounters=encounters,
    )
    return raid, True
