"""Capture known players + known encounters from successful tool calls (feature 007 / US1).

Fed by the tool-success hub (``ws.py:_handle_tool_end``) alongside the raid/graph/artifact
captures. Pure extractors (``players_from_tool`` / ``encounters_from_find``) turn a tool
record into typed rows; the async ``capture_*`` functions upsert them per tenant. Both are
strictly **best-effort**: any failure is logged and swallowed so a capture never blocks or
fails the turn (FR-008). Writes participate in the existing commit-and-rescope guard.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repository as repo

logger = logging.getLogger(__name__)

# Tools whose args carry an unambiguous (name, server, region) character identity.
_PLAYER_RANKING_TOOLS = frozenset(
    {"get_character_zone_rankings", "get_character_encounter_rankings"}
)


def players_from_tool(name: str, ok: bool, args: dict, result: dict | None) -> list[dict]:
    """Extract known-player rows from a successful character-ranking tool call.

    Identity (name/server/region) comes from the call args — the only source that carries
    all three unambiguously. ``get_report_master_data`` actors are intentionally NOT
    captured: they expose only a display name (no server/region), so they cannot form the
    required unambiguous identity (data-model §1 skip rule).
    """
    if not ok or name not in _PLAYER_RANKING_TOOLS:
        return []
    result = result or {}
    if result.get("status") != "success":
        return []
    args = args or {}
    char_name = (result.get("name") or args.get("name") or "").strip()
    server = (args.get("server") or "").strip()
    region = (args.get("region") or "").strip()
    if not char_name or not server or not region:
        return []  # identity must be unambiguous
    return [
        {
            "name": char_name,
            "server": server,
            "region": region.upper(),
            "source": "ranking",
        }
    ]


def encounters_from_find(name: str, ok: bool, result: dict | None) -> list[dict]:
    """Extract known-encounter rows from a successful ``find_encounter`` call.

    Only matches with a numeric ``encounter_id`` are kept; name-only matches without a
    stable id are skipped (dedup requires an id — data-model §2 / spec edge case).
    """
    if name != "find_encounter" or not ok:
        return []
    result = result or {}
    if result.get("status") != "success":
        return []
    matches = result.get("matches")
    if not isinstance(matches, list):
        return []
    rows: list[dict] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        enc_id = m.get("encounter_id")
        if not isinstance(enc_id, int) or enc_id == 0:
            continue  # name-only / non-encounter match — not cacheable
        rows.append(
            {
                "encounter_id": enc_id,
                "encounter_name": m.get("encounter") or f"Encounter {enc_id}",
                "zone_id": m.get("zone_id") if isinstance(m.get("zone_id"), int) else None,
                "zone_name": m.get("zone"),
            }
        )
    return rows


async def capture_players_from_tool(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    ok: bool,
    args: dict,
    result: dict | None,
    conversation_id: uuid.UUID | None,
) -> int:
    """Upsert known players discovered in this tool record. Returns the count (0 when N/A).

    Best-effort: a unique-violation or any other error rolls back only this capture's
    savepoint, never the sibling captures or the turn.
    """
    players = players_from_tool(name, ok, args, result)
    if not players:
        return 0
    try:
        async with session.begin_nested():
            for p in players:
                await repo.upsert_known_player(session, tenant_id=tenant_id, **p)
        return len(players)
    except Exception:  # noqa: BLE001 - capture is best-effort; never break the turn
        logger.exception("known-player capture failed for tool %s", name)
        return 0


async def capture_encounters_from_tool(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    ok: bool,
    args: dict,
    result: dict | None,
    conversation_id: uuid.UUID | None,
) -> int:
    """Upsert known encounters resolved in this tool record. Returns the count (0 when N/A)."""
    encounters = encounters_from_find(name, ok, result)
    if not encounters:
        return 0
    try:
        async with session.begin_nested():
            for e in encounters:
                await repo.upsert_known_encounter(session, tenant_id=tenant_id, **e)
        return len(encounters)
    except Exception:  # noqa: BLE001 - capture is best-effort; never break the turn
        logger.exception("known-encounter capture failed for tool %s", name)
        return 0
