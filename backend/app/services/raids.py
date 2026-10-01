"""Raid tracking (US1): turn successful report retrievals into TrackedRaid rows.

Fed by the agent-runner backbone (see agent_runner.stream_response): every tool
record is offered here; when a *report-scoped* tool returns successfully for a
``report_code``, we upsert a TrackedRaid. The report label is resolved lazily
(one extra GraphQL call) only the first time a raid is seen, so re-references are
cheap.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.report_tools import get_report_metadata

from ..db import repository as repo
from ..db.models import TrackedRaid

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


async def capture_raid_from_tool(
    session: AsyncSession,
    *,
    name: str,
    ok: bool,
    args: dict,
    conversation_id: uuid.UUID | None,
) -> TrackedRaid | None:
    """Upsert a TrackedRaid if this tool record is a successful report retrieval.

    Returns the raid (so the caller can emit a ``raid_tracked`` frame), or ``None``
    when the record isn't a successful report-scoped call.
    """
    if not ok or name not in REPORT_SCOPED_TOOLS:
        return None
    report_code = (args or {}).get("report_code")
    if not report_code or not isinstance(report_code, str):
        return None

    existing = await repo.get_tracked_raid(session, report_code)
    if existing is not None:
        # Known raid — just touch recency (no extra WCL call).
        return await repo.upsert_tracked_raid(
            session,
            report_code=report_code,
            label=existing.label,
            conversation_id=conversation_id,
        )

    # First time we've seen this report — resolve its label off the event loop.
    try:
        meta = await asyncio.to_thread(get_report_metadata, report_code)
    except Exception:  # noqa: BLE001 - metadata is best-effort; fall back to the code
        meta = {"status": "error"}
    label, zone, guild, started = _build_label(report_code, meta)
    return await repo.upsert_tracked_raid(
        session,
        report_code=report_code,
        label=label,
        zone=zone,
        guild=guild,
        report_started_at=started,
        conversation_id=conversation_id,
    )
