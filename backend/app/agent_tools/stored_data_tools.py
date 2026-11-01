"""The agent's exact lookups in stored Warcraft Logs data (feature 045, sc-131).

Every read goes through the 039 visibility rule (``read_visible_fetch`` for one exact query,
``list_visible_summaries`` for the summaries list), so a tool never shows a row the workspace
may not be served, and a row it may not see answers exactly like one that was never stored:
the agent falls back to the WCL tools and learns nothing about other workspaces' data. No
embeddings: semantic search is ``search_knowledge`` (044). Names go through the shared
resolver. Who is asking comes only from the authenticated chat turn, like the profile tool.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from google.adk.tools import ToolContext

from wcl_agent.capabilities import ToolGroup
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import _flight_key
from wcl_agent.tools.report_tools import (
    HOSTILITY_TYPES,
    TABLE_DATA_TYPES,
    _acap,
    _fight_ids,
    _summary_from,
    report_query,
)

from ..config import settings
from ..repositories.raw_fetches import list_visible_summaries, read_visible_fetch
from ..services.name_resolver import ResolutionError, name_key, resolve_character, resolve_encounter
from ..services.raw_fetch_reads import is_fresh
from ..tenancy.context import RequestIdentity, current_identity, tenant_scope

logger = logging.getLogger(__name__)

MAX_FIGHTS = 100
MAX_REPORTS = 25
SUMMARY_SCAN = 200  # newest visible summaries searched for a character

NOT_STORED = {
    "status": "not_stored",
    "message": "Not stored locally. Use the WCL report tools for this.",
}
_UNAVAILABLE = {"status": "error", "error_message": "Stored data is unavailable in this session."}
_FAILED = {"status": "error", "error_message": "Couldn't read the stored data. Use the WCL report tools."}


def _identity(tool_context: ToolContext) -> RequestIdentity | None:
    identity = current_identity.get()
    if identity is None or identity.tenant_id is None or str(identity.tenant_id) != tool_context.user_id:
        return None
    return identity


def _since(now: datetime) -> datetime:
    return now - timedelta(days=settings.raw_store_reverify_days)


async def _read(identity: RequestIdentity, query: str, variables: dict[str, Any]) -> dict[str, Any] | None:
    """The stored body of exactly this query, under the visibility and freshness rules."""
    now = datetime.now(UTC)
    async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as session:
        body = await read_visible_fetch(
            session, _flight_key(query, variables), tenant_id=identity.tenant_id,
            since=_since(now), fresh=lambda fetched_at, statuses: is_fresh(fetched_at, statuses, now=now),
        )
    return None if body is None else await asyncio.to_thread(json.loads, body)


def _report(body: dict[str, Any] | None) -> dict[str, Any] | None:
    report = ((body or {}).get("data") or {}).get("reportData") or {}
    found = report.get("report")
    return found if isinstance(found, dict) else None


async def list_stored_fights(report_code: str, encounter: str = "", tool_context: ToolContext = None) -> dict:
    """List a report's fights from stored data, without calling Warcraft Logs.

    Args:
        report_code: The report code.
        encounter: Optional boss name or id; only its fights are listed.

    Returns {"status": "success", "fights": [...]} (id, name, encounter_id, difficulty, kill,
    size, start_time_ms; at most 100) or {"status": "not_stored"}: then use get_report_fights.
    """
    identity = _identity(tool_context)
    if identity is None:
        return dict(_UNAVAILABLE)
    code = report_code.strip()
    try:
        encounter_id = None
        if encounter.strip():
            async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as session:
                resolved, _ = await resolve_encounter(encounter, session=session, tenant_id=identity.tenant_id)
            encounter_id = resolved.id
        report = _report(await _read(identity, REPORT_SUMMARY, {"code": code}))
    except ResolutionError as exc:
        return {"status": "error", "error_message": str(exc), "matches": list(exc.matches)}
    except Exception:  # a plain tool error, so the turn goes on; never the exception text
        logger.exception("list_stored_fights failed")
        return dict(_FAILED)
    if report is None:
        return dict(NOT_STORED)
    summary = _summary_from(code, report)
    fights = [
        {"id": f.id, "name": f.name, "encounter_id": f.encounter_id, "difficulty": f.difficulty,
         "kill": f.kill, "size": f.size, "start_time_ms": f.start_time_ms}
        for f in summary.fights
        if encounter_id is None or f.encounter_id == encounter_id
    ]
    return {
        "status": "success",
        "report_code": code,
        "title": summary.title,
        "fights": fights[:MAX_FIGHTS],
        "truncated": len(fights) > MAX_FIGHTS,
    }


async def get_stored_fight_table(
    report_code: str,
    data_type: str,
    fight_id: int = 0,
    source_id: int = 0,
    ability_id: int = 0,
    hostility_type: str = "Friendlies",
    tool_context: ToolContext = None,
) -> dict:
    """Get a stored analysis table for a report fight, without calling Warcraft Logs.

    Same arguments as get_report_table (data_type e.g. DamageDone, Healing, Casts, Deaths;
    fight_id 0 = all fights; source_id 0 = all players). Returns {"status": "success",
    "table": ...}, capped like get_report_table, or {"status": "not_stored"}: then use
    get_report_table.
    """
    identity = _identity(tool_context)
    if identity is None:
        return dict(_UNAVAILABLE)
    if data_type not in TABLE_DATA_TYPES:
        return {"status": "error", "error_message": f"Bad data_type '{data_type}'.", "valid": sorted(TABLE_DATA_TYPES)}
    if hostility_type not in HOSTILITY_TYPES:
        return {"status": "error", "error_message": f"Bad hostility_type '{hostility_type}'.",
                "valid": sorted(HOSTILITY_TYPES)}
    # Exactly the request get_report_table sends, so its stored answer has this key.
    field = (
        f"table(dataType: {data_type}, hostilityType: {hostility_type}, "
        "fightIDs: $fightIDs, sourceID: $sourceID, abilityID: $abilityID)"
    )
    var_decls = ", $fightIDs: [Int], $sourceID: Int, $abilityID: Float"
    variables = {
        "code": report_code.strip(),
        "fightIDs": _fight_ids(fight_id),
        "sourceID": source_id or None,
        "abilityID": ability_id or None,
    }
    query = report_query(f"endTime {field}" if source_id else field, var_decls)
    try:
        report = _report(await _read(identity, query, variables))
    except Exception:
        logger.exception("get_stored_fight_table failed")
        return dict(_FAILED)
    if report is None or report.get("table") is None:
        return dict(NOT_STORED)
    return {"status": "success", "data_type": data_type, "table": await _acap(report["table"])}


async def list_stored_reports_for_character(character: str, tool_context: ToolContext = None) -> dict:
    """List stored reports a character appears in, newest first, without calling Warcraft Logs.

    Args:
        character: The character's name, or "Name-Realm".

    Returns {"status": "success", "reports": [...]} (code, title, start_time_ms, zone; at most
    25) or {"status": "not_stored"}: then use the WCL character tools.
    """
    identity = _identity(tool_context)
    if identity is None:
        return dict(_UNAVAILABLE)
    try:
        async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as session:
            person = await resolve_character(character, session=session, tenant_id=identity.tenant_id)
            bodies = await list_visible_summaries(
                session, tenant_id=identity.tenant_id, since=_since(datetime.now(UTC)), limit=SUMMARY_SCAN
            )
        reports = await asyncio.to_thread(_reports_with, bodies, person.key)
    except ResolutionError as exc:
        return {"status": "error", "error_message": str(exc), "matches": list(exc.matches)}
    except Exception:
        logger.exception("list_stored_reports_for_character failed")
        return dict(_FAILED)
    if not reports:
        return dict(NOT_STORED)
    return {"status": "success", "character": person.name, "reports": reports[:MAX_REPORTS]}


def _reports_with(bodies: list[bytes], key: str) -> list[dict[str, Any]]:
    """Reports (single or batch summaries) whose roster names the character, deduplicated."""
    seen: dict[str, dict[str, Any]] = {}
    for body in bodies:
        report_data = (json.loads(body).get("data") or {}).get("reportData") or {}
        for report in report_data.values():
            if not isinstance(report, dict) or not isinstance(report.get("code"), str):
                continue
            actors = (report.get("masterData") or {}).get("actors") or []
            if report["code"] in seen or not any(name_key(a.get("name") or "") == key for a in actors):
                continue
            seen[report["code"]] = {
                "code": report["code"],
                "title": report.get("title"),
                "start_time_ms": report.get("startTime"),
                "zone": (report.get("zone") or {}).get("name"),
            }
    return sorted(seen.values(), key=lambda r: r["start_time_ms"] or 0, reverse=True)


STORED_DATA_TOOLS = ToolGroup(
    "Stored data",
    (list_stored_fights, get_stored_fight_table, list_stored_reports_for_character),
)
