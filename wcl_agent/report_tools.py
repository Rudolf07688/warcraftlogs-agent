"""Deep-dive ADK tools over the Warcraft Logs v2 API.

The rankings tools (``tools.py``) only see the leaderboard. These tools open up
the rest of the API so the agent can answer essentially any question:

* ``reportData.report`` — per-fight **tables** (damage/healing/casts/buffs/
  debuffs/deaths by ability and source), **events**, **graphs**, per-fight
  **rankings**, **playerDetails** (gear/talents), and **masterData** (actor and
  ability id maps).
* ``characterData.character`` — an individual player's parse history.
* ``run_wcl_graphql`` — a raw query escape hatch for anything not covered above.

Every field WCL returns as a ``JSON`` scalar is passed straight back to the model
(size-capped), so these tools stay robust even as the JSON shape varies by zone.
All return a ``dict`` with a ``"status"`` key. They are coroutines (feature 013): WCL
I/O is awaited on the event loop, so ADK runs parallel tool calls concurrently.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from .cache import (
    CacheFamily,
    family_ttl,
    get_many_or_load,
    get_or_load,
    get_refresh_actor,
    keys,
    try_claim_refresh,
    unfinished_ttl,
)
from .cache_models import (
    CharacterRankings,
    CharacterRef,
    FightSummary,
    PlayerRef,
    PlayerTable,
    ReportSummary,
)
from .constants import METRICS
from .normalize import is_finished, server_slug
from .queries import CHARACTER_REF, REPORT_SUMMARY, character_refs_query, report_summaries_query
from .provenance import Completeness, Provenance, flatten_report_rankings, with_envelope
from . import wcl_client

# --- Enum whitelists (inlined into queries after validation) ------------------
# Match the live API enums (feature 009, research R5/R14): ``Resurrections`` is
# not a valid TableDataType or EventDataType; ``Summons`` is valid for tables.
TABLE_DATA_TYPES = {
    "Summary", "DamageDone", "DamageTaken", "Healing", "Casts", "Deaths",
    "Debuffs", "Buffs", "Dispels", "Interrupts", "Resources", "Threat",
    "Survivability", "Summons",
}
EVENT_DATA_TYPES = {
    "All", "DamageDone", "DamageTaken", "Healing", "Casts", "Deaths", "Debuffs",
    "Buffs", "Dispels", "Interrupts", "Resources", "Threat",
    "CombatantInfo", "Summons",
}
GRAPH_DATA_TYPES = TABLE_DATA_TYPES
HOSTILITY_TYPES = {"Friendlies", "Enemies"}
KILL_TYPES = {"All", "Encounters", "Kills", "Wipes", "Trash"}

MAX_JSON_CHARS = 60000  # keep tool results from blowing up the model context


def _cap(obj: Any) -> Any:
    """Return obj as-is, or a truncated-with-note form if it's too large."""
    text = json.dumps(obj, default=str)
    if len(text) <= MAX_JSON_CHARS:
        return obj
    return {
        "_truncated": True,
        "_note": (
            "Result too large to return in full. Narrow the query "
            "(set fight_id, source_id, or ability_id, reduce limit, or request a "
            "more specific data_type) and try again."
        ),
        "_preview": text[:MAX_JSON_CHARS],
    }


async def _acap(obj: Any) -> Any:
    """``_cap`` off the event loop: sizing a large result is a full ``json.dumps`` (SC-008)."""
    return await asyncio.to_thread(_cap, obj)


async def _report_fields(
    code: str, field_calls: str, var_decls: str, variables: dict[str, Any]
) -> dict[str, Any] | None:
    """Run ``reportData.report(code:){ <field_calls> }`` and return the report object."""
    query = (
        f"query ReportQ($code: String!{var_decls}) {{ "
        f"reportData {{ report(code: $code) {{ {field_calls} }} }} }}"
    )
    data = await wcl_client.get_async_client().query(query, {"code": code, **variables})
    return ((data.get("data") or {}).get("reportData") or {}).get("report")


async def _report_field(
    code: str,
    field_call: str,
    var_decls: str,
    variables: dict[str, Any],
    field_name: str,
) -> Any:
    """Run ``reportData.report(code:){ <field_call> }`` and return that field."""
    report = await _report_fields(code, field_call, var_decls, variables)
    if report is None:
        return None
    return report.get(field_name)


def _report_ttl(family: CacheFamily, end_time_ms: int | None) -> int:
    """Finished reports keep the family TTL; one still being logged only briefly (FR-005)."""
    if end_time_ms is not None and is_finished(end_time_ms):
        return family_ttl(family)
    return unfinished_ttl()


def _summary_from(code: str, report: dict[str, Any]) -> ReportSummary:
    actors = ((report.get("masterData") or {}).get("actors")) or []
    zone = report.get("zone") or {}
    return ReportSummary(
        code=code,
        title=report.get("title"),
        start_time_ms=report["startTime"],
        end_time_ms=report["endTime"],
        zone_id=zone.get("id"),
        zone_name=zone.get("name"),
        guild_name=(report.get("guild") or {}).get("name"),
        players={a["id"]: PlayerRef(name=a["name"], class_name=a.get("subType")) for a in actors},
        fights=[
            FightSummary(
                id=f["id"],
                name=f["name"],
                encounter_id=f.get("encounterID"),
                difficulty=f.get("difficulty"),
                kill=f.get("kill"),
                average_item_level=f.get("averageItemLevel"),
                size=f.get("size"),
                player_ids=list(f.get("friendlyPlayers") or []),
            )
            for f in report.get("fights") or []
        ],
    )


def _summary_ttl(summary: ReportSummary) -> int:
    return _report_ttl(CacheFamily.REPORT_SUMMARY, summary.end_time_ms)


async def load_report_summary(code: str) -> ReportSummary | None:
    """A report's fights, bosses, kills/wipes and roster (``report_summary``), or None."""
    code = code.strip()

    async def load() -> ReportSummary | None:
        data = await wcl_client.get_async_client().query(REPORT_SUMMARY, {"code": code})
        report = ((data.get("data") or {}).get("reportData") or {}).get("report")
        return _summary_from(code, report) if report else None

    return await get_or_load(
        CacheFamily.REPORT_SUMMARY, keys.report_summary(code), ReportSummary, load, ttl=_summary_ttl
    )


async def load_report_summaries(codes: Sequence[str]) -> list[ReportSummary | None]:
    """Several reports' summaries; the uncached ones in ONE request (PERF-001).

    A report WCL can't return (deleted, private) fails the whole batched GraphQL request
    with ``RuntimeError``; callers fall back to :func:`load_report_summary` per code.
    """
    codes = [c.strip() for c in codes]

    async def load(missing: list[int]) -> list[ReportSummary | None]:
        variables = {f"c{j}": codes[i] for j, i in enumerate(missing)}
        data = await wcl_client.get_async_client().query(report_summaries_query(len(missing)), variables)
        reports = ((data.get("data") or {}).get("reportData")) or {}
        return [
            _summary_from(codes[i], reports[f"r{j}"]) if reports.get(f"r{j}") else None
            for j, i in enumerate(missing)
        ]

    return await get_many_or_load(
        CacheFamily.REPORT_SUMMARY, [keys.report_summary(c) for c in codes], ReportSummary, load,
        ttl=_summary_ttl,
    )


def _fight_ids(fight_id: int) -> list[int] | None:
    """0 means 'all fights'; otherwise a single-fight filter list."""
    return [fight_id] if fight_id else None


# --- Report structure ---------------------------------------------------------

async def get_report_fights(report_code: str) -> dict[str, Any]:
    """List the fights (pulls) in a Warcraft Logs report, with the players in each.

    Use this to turn a report code (e.g. from a leaderboard parse) into fight IDs
    and player source IDs, which the other report tools need. Report codes are the
    short string in a log URL: warcraftlogs.com/reports/<CODE>.

    Args:
        report_code (str): The report code.

    Returns:
        dict: {"status": "success", "title": ..., "zone": ..., "guild": ...,
               "start_time_ms": ..., "players": {id: {"name", "class"}},
               "fights": [{id, name, encounterID, difficulty, kill,
                           averageItemLevel, players:[names]}]} or an error.
    """
    try:
        summary = await load_report_summary(report_code)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if summary is None:
        return {"status": "error", "error_message": f"No report '{report_code}'."}

    players = {pid: {"name": p.name, "class": p.class_name} for pid, p in summary.players.items()}
    fights = [
        {
            "id": f.id,
            "name": f.name,
            "encounterID": f.encounter_id,
            "difficulty": f.difficulty,
            "kill": f.kill,
            "averageItemLevel": f.average_item_level,
            "size": f.size,
            "players": [players[i]["name"] for i in f.player_ids if i in players],
        }
        for f in summary.fights
    ]
    zone = (
        {"id": summary.zone_id, "name": summary.zone_name}
        if summary.zone_id is not None or summary.zone_name is not None
        else None
    )
    return with_envelope(
        {
            "status": "success",
            "title": summary.title,
            "zone": zone,
            # Also lets the backend label a tracked raid without a second query (PERF-016).
            "guild": summary.guild_name,
            "start_time_ms": summary.start_time_ms,
            "players": players,
            "fights": await _acap(fights),
        },
        Provenance(report_code=report_code),
    )


async def get_report_master_data(report_code: str) -> dict[str, Any]:
    """Get the actor (player/NPC/pet) and ability id->name maps for a report.

    Useful for resolving source_id / ability_id values used by the table, events,
    and graph tools.

    Args:
        report_code (str): The report code.

    Returns:
        dict: {"status": "success", "actors": [...], "abilities": [...]} or error.
    """
    query = """
    query ReportMaster($code: String!) {
      reportData { report(code: $code) { masterData {
        actors { id name type subType }
        abilities { gameID name type }
      } } }
    }
    """.strip()
    try:
        data = await wcl_client.get_async_client().query(query, {"code": report_code})
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    md = (((data.get("data") or {}).get("reportData") or {}).get("report") or {}).get("masterData")
    if md is None:
        return {"status": "error", "error_message": f"No report '{report_code}'."}
    return with_envelope(
        {"status": "success", "actors": await _acap(md.get("actors")), "abilities": await _acap(md.get("abilities"))},
        Provenance(report_code=report_code),
    )


async def get_report_metadata(report_code: str) -> dict[str, Any]:
    """Resolve a report's human-readable metadata in a single GraphQL call.

    Used to label a tracked raid (``"<guild> — <zone> — <date>"``). Not exposed to
    the agent as a tool — called server-side when a raid is first captured.

    Args:
        report_code (str): The report code.

    Returns:
        dict: {"status": "success", "title", "zone", "guild", "start_time_ms"} or
            an error dict. ``zone``/``guild`` may be ``None`` for some reports.
    """
    try:
        summary = await load_report_summary(report_code)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if summary is None:
        return {"status": "error", "error_message": f"No report '{report_code}'."}
    return {
        "status": "success",
        "title": summary.title,
        "zone": summary.zone_name,
        "guild": summary.guild_name,
        "start_time_ms": summary.start_time_ms,
    }


# --- The workhorses: table / events / graph -----------------------------------

async def get_report_table(
    report_code: str,
    data_type: str,
    fight_id: int = 0,
    source_id: int = 0,
    ability_id: int = 0,
    hostility_type: str = "Friendlies",
) -> dict[str, Any]:
    """Get an analysis table for a report — the richest general-purpose tool.

    This is the data behind the Warcraft Logs website tabs. Depending on
    data_type it breaks a fight down by ability and by source/target, e.g.:
    - 'DamageDone' / 'Healing': totals per player, with per-ability breakdowns.
      Set source_id to one player to see WHICH SPELLS contribute their damage.
    - 'Casts': how many times each ability was cast.
    - 'Buffs' / 'Debuffs': uptime of each aura.
    - 'Deaths': who died, when, and to what.
    - 'DamageTaken': damage taken per source (set hostility_type='Enemies' to see
      what the boss/adds did).

    Args:
        report_code (str): The report code.
        data_type (str): One of Summary, DamageDone, DamageTaken, Healing, Casts,
            Deaths, Debuffs, Buffs, Dispels, Interrupts, Resources, Threat,
            Survivability, Summons.
        fight_id (int): A single fight id (from get_report_fights). 0 = all fights.
        source_id (int): Filter to one actor id (0 = all). Use this to drill into
            one player's abilities.
        ability_id (int): Filter to one ability's game id (0 = all).
        hostility_type (str): 'Friendlies' (players) or 'Enemies' (NPCs/boss).

    Returns:
        dict: {"status": "success", "data_type": ..., "table": {...},
               "provenance": {...}, "completeness": {...}} or an error.
            ``completeness.truncated`` is true when the table was too large and
            only a preview is returned — narrow the query before drawing
            completeness-dependent conclusions.
    """
    if data_type not in TABLE_DATA_TYPES:
        return {"status": "error", "error_message": f"Bad data_type '{data_type}'.",
                "valid": sorted(TABLE_DATA_TYPES)}
    if hostility_type not in HOSTILITY_TYPES:
        return {"status": "error", "error_message": f"Bad hostility_type '{hostility_type}'.",
                "valid": sorted(HOSTILITY_TYPES)}
    field = (
        f"table(dataType: {data_type}, hostilityType: {hostility_type}, "
        "fightIDs: $fightIDs, sourceID: $sourceID, abilityID: $abilityID)"
    )
    var_decls = ", $fightIDs: [Int], $sourceID: Int, $abilityID: Float"
    variables = {
        "fightIDs": _fight_ids(fight_id),
        "sourceID": source_id or None,
        "abilityID": ability_id or None,
    }
    try:
        if source_id:
            table = await _player_table(
                report_code, field, var_decls, variables,
                keys.report_player(report_code, source_id, data_type, fight_id, ability_id, hostility_type),
            )
        else:  # whole-raid tables are large and rarely repeated: not cached
            table = await _report_field(report_code, field, var_decls, variables, "table")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if table is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return with_envelope(
        {"status": "success", "data_type": data_type, "table": await _acap(table)},
        Provenance(report_code=report_code, fight_id=fight_id or None, source_id=source_id or None),
    )


async def _player_table(
    code: str, field: str, var_decls: str, variables: dict[str, Any], key: str
) -> Any:
    """One player's table (``report_player``); ``endTime`` rides along to pick the TTL."""
    end_time: dict[str, int | None] = {"ms": None}

    async def load() -> PlayerTable | None:
        report = await _report_fields(code, f"endTime {field}", var_decls, variables)
        if report is None or report.get("table") is None:
            return None
        end_time["ms"] = report.get("endTime")
        return PlayerTable(data=report["table"])

    cached = await get_or_load(
        CacheFamily.REPORT_PLAYER, key, PlayerTable, load,
        ttl=lambda _: _report_ttl(CacheFamily.REPORT_PLAYER, end_time["ms"]),
    )
    return None if cached is None else cached.data


async def get_report_events(
    report_code: str,
    data_type: str,
    fight_id: int = 0,
    source_id: int = 0,
    ability_id: int = 0,
    hostility_type: str = "Friendlies",
    limit: int = 100,
    start_time: int = 0,
) -> dict[str, Any]:
    """Get the raw combat event stream for a report (paginated).

    Use for granular questions the summary tables can't answer (exact timings,
    sequences, individual hits). Prefer get_report_table for aggregates. Always
    scope with fight_id + source_id to keep results small.

    Args:
        report_code (str): The report code.
        data_type (str): One of All, DamageDone, DamageTaken, Healing, Casts,
            Deaths, Debuffs, Buffs, Dispels, Interrupts, Resources, Threat,
            CombatantInfo, Summons.
        fight_id (int): Single fight id (0 = all).
        source_id (int): Actor id filter (0 = all).
        ability_id (int): Ability game id filter (0 = all).
        hostility_type (str): 'Friendlies' or 'Enemies'.
        limit (int): Max events per page (1-500).
        start_time (int): Report-relative ms to start from; pass the previous
            call's nextPageTimestamp to page forward. 0 = fight start.

    Returns:
        dict: {"status": "success", "events": {data:[...], nextPageTimestamp},
               "provenance": {...}, "completeness": {"has_more": bool, ...}} or
            error. ``completeness.has_more`` is true when another page exists
            (pass ``nextPageTimestamp`` as ``start_time`` to continue).
    """
    if data_type not in EVENT_DATA_TYPES:
        return {"status": "error", "error_message": f"Bad data_type '{data_type}'.",
                "valid": sorted(EVENT_DATA_TYPES)}
    if hostility_type not in HOSTILITY_TYPES:
        return {"status": "error", "error_message": f"Bad hostility_type '{hostility_type}'.",
                "valid": sorted(HOSTILITY_TYPES)}
    limit = max(1, min(int(limit or 100), 500))
    # `events` returns a ReportEventPaginator object, not a JSON scalar, so it
    # needs an explicit sub-selection (the `data` field is the JSON scalar).
    field = (
        f"events(dataType: {data_type}, hostilityType: {hostility_type}, "
        "fightIDs: $fightIDs, sourceID: $sourceID, abilityID: $abilityID, "
        "limit: $limit, startTime: $startTime) { data nextPageTimestamp }"
    )
    var_decls = (
        ", $fightIDs: [Int], $sourceID: Int, $abilityID: Float, "
        "$limit: Int, $startTime: Float"
    )
    variables = {
        "fightIDs": _fight_ids(fight_id),
        "sourceID": source_id or None,
        "abilityID": ability_id or None,
        "limit": limit,
        "startTime": start_time or None,
    }
    try:
        events = await _report_field(report_code, field, var_decls, variables, "events")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if events is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    has_more = isinstance(events, dict) and events.get("nextPageTimestamp") is not None
    return with_envelope(
        {"status": "success", "data_type": data_type, "events": await _acap(events)},
        Provenance(report_code=report_code, fight_id=fight_id or None, source_id=source_id or None),
        Completeness(has_more=has_more),
    )


async def get_report_graph(
    report_code: str,
    data_type: str,
    fight_id: int = 0,
    source_id: int = 0,
    hostility_type: str = "Friendlies",
) -> dict[str, Any]:
    """Get a time-series graph (e.g. DPS/HPS over time, resources) for a fight.

    Args:
        report_code (str): The report code.
        data_type (str): Same set as get_report_table (e.g. DamageDone, Healing,
            Resources).
        fight_id (int): Single fight id (0 = all).
        source_id (int): Actor id filter (0 = all).
        hostility_type (str): 'Friendlies' or 'Enemies'.

    Returns:
        dict: {"status": "success", "graph": {...}} or an error.
    """
    if data_type not in GRAPH_DATA_TYPES:
        return {"status": "error", "error_message": f"Bad data_type '{data_type}'.",
                "valid": sorted(GRAPH_DATA_TYPES)}
    if hostility_type not in HOSTILITY_TYPES:
        return {"status": "error", "error_message": f"Bad hostility_type '{hostility_type}'.",
                "valid": sorted(HOSTILITY_TYPES)}
    field = (
        f"graph(dataType: {data_type}, hostilityType: {hostility_type}, "
        "fightIDs: $fightIDs, sourceID: $sourceID)"
    )
    var_decls = ", $fightIDs: [Int], $sourceID: Int"
    variables = {"fightIDs": _fight_ids(fight_id), "sourceID": source_id or None}
    try:
        graph = await _report_field(report_code, field, var_decls, variables, "graph")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if graph is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return with_envelope(
        {"status": "success", "data_type": data_type, "graph": await _acap(graph)},
        Provenance(report_code=report_code, fight_id=fight_id or None, source_id=source_id or None),
    )


RANKING_COMPARE_TYPES = {"Rankings", "Parses"}
RANKING_TIMEFRAMES = {"Historical", "Today"}


async def get_report_rankings(
    report_code: str,
    fight_id: int = 0,
    compare: str = "Rankings",
    timeframe: str = "Historical",
) -> dict[str, Any]:
    """Get the parse percentiles for the players in a report's fight(s), with context.

    A percentile depends on what it is compared against (feature 009, FR-018):
    - compare='Rankings' (default): against every character's BEST score for the
      tier (what the WCL rankings pages show). compare='Parses': against all
      individual pulls logged in roughly the last two weeks, i.e. typical
      execution rather than best scores — percentiles are usually higher.
    - timeframe='Historical' (default): as evaluated at the time of the kill.
      timeframe='Today': re-evaluated against the current population.
    Say which pair you used when it matters. The result's `percentiles` list is a
    flattened row per ranked player with both the overall `rank_percent` and the
    item-level `bracket_percent`, the population size `total_parses`, partition,
    and fight context — present overall and bracket together when both exist.

    Args:
        report_code (str): The report code.
        fight_id (int): Single fight id (0 = all fights).
        compare (str): 'Rankings' or 'Parses'.
        timeframe (str): 'Historical' or 'Today'.

    Returns:
        dict: {"status": "success", "rankings": {...raw...}, "percentiles": [
            {name, server, class_name, spec, role, population, timeframe,
             rank_percent, bracket_percent, bracket, item_level, total_parses,
             partition, metric, encounter_id, difficulty, fight_id, kill,
             duration_s, amount}], "provenance": {...compare, timeframe...},
            "completeness": {...}} or an error.
    """
    if compare not in RANKING_COMPARE_TYPES:
        return {"status": "error", "error_message": f"Bad compare '{compare}'.",
                "valid": sorted(RANKING_COMPARE_TYPES)}
    if timeframe not in RANKING_TIMEFRAMES:
        return {"status": "error", "error_message": f"Bad timeframe '{timeframe}'.",
                "valid": sorted(RANKING_TIMEFRAMES)}
    field = f"rankings(fightIDs: $fightIDs, compare: {compare}, timeframe: {timeframe})"
    var_decls = ", $fightIDs: [Int]"
    try:
        rankings = await _report_field(
            report_code, field, var_decls, {"fightIDs": _fight_ids(fight_id)}, "rankings"
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if rankings is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    percentiles = [
        asdict(p)
        for p in flatten_report_rankings(rankings, compare=compare, timeframe=timeframe, metric="default")
    ]
    return with_envelope(
        {"status": "success", "rankings": await _acap(rankings), "percentiles": await _acap(percentiles)},
        Provenance(report_code=report_code, fight_id=fight_id or None, compare=compare, timeframe=timeframe),
    )


async def get_report_player_details(report_code: str, fight_id: int = 0) -> dict[str, Any]:
    """Get player gear, talents, specs, and roles for a report's fight(s).

    Args:
        report_code (str): The report code.
        fight_id (int): Single fight id (0 = all fights).

    Returns:
        dict: {"status": "success", "playerDetails": {...}} or an error.
    """
    field = "playerDetails(fightIDs: $fightIDs)"
    var_decls = ", $fightIDs: [Int]"
    try:
        details = await _report_field(
            report_code, field, var_decls, {"fightIDs": _fight_ids(fight_id)}, "playerDetails"
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if details is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return with_envelope(
        {"status": "success", "playerDetails": await _acap(details)},
        Provenance(report_code=report_code, fight_id=fight_id or None),
    )


# --- Individual character history ---------------------------------------------

_server_slug = server_slug  # feature 014: moved to normalize (shared with the cache keys)


def _character_ref_from(char: dict[str, Any], name: str, server: str, region: str) -> CharacterRef:
    srv = char.get("server") or {}
    return CharacterRef(
        id=char["id"],
        name=char.get("name") or name.strip(),
        realm=srv.get("slug") or server_slug(server),
        region=((srv.get("region") or {}).get("slug") or region).strip().lower(),
        class_id=char.get("classID"),
    )


async def resolve_character(name: str, server: str, region: str) -> CharacterRef | None:
    """A character's WCL identity, or None when WCL has no such character (``char_id``).

    Cached for everyone for a day; an unknown name is remembered briefly, so a mistyped
    name asked again costs no WCL request.
    """

    async def load() -> CharacterRef | None:
        variables = {"name": name.strip(), "server": server_slug(server), "region": region.strip().upper()}
        data = await wcl_client.get_async_client().query(CHARACTER_REF, variables)
        char = ((data.get("data") or {}).get("characterData") or {}).get("character")
        return _character_ref_from(char, name, server, region) if char else None

    return await get_or_load(CacheFamily.CHAR_ID, keys.char_id(region, server, name), CharacterRef, load)


async def resolve_characters(chars: Sequence[tuple[str, str, str]]) -> list[CharacterRef | None]:
    """:func:`resolve_character` for several (name, server, region); unknown ones in ONE request."""

    async def load(missing: list[int]) -> list[CharacterRef | None]:
        variables: dict[str, Any] = {}
        for j, i in enumerate(missing):
            name, server, region = chars[i]
            variables.update({f"n{j}": name.strip(), f"s{j}": server_slug(server), f"r{j}": region.strip().upper()})
        data = await wcl_client.get_async_client().query(character_refs_query(len(missing)), variables)
        nodes = ((data.get("data") or {}).get("characterData")) or {}
        return [
            _character_ref_from(nodes[f"c{j}"], *chars[i]) if nodes.get(f"c{j}") else None
            for j, i in enumerate(missing)
        ]

    return await get_many_or_load(
        CacheFamily.CHAR_ID, [keys.char_id(r, s, n) for n, s, r in chars], CharacterRef, load
    )


async def _character_rankings(
    name: str, server: str, region: str, scope: str, field_call: str, var_decls: str,
    variables: dict[str, Any], key_for: Any, force_refresh: bool,
) -> tuple[CharacterRankings, str | None] | dict[str, Any]:
    """Shared body of the two character-ranking tools: resolve, then a cached lookup by id.

    Returns (rankings, refresh outcome) — the outcome is "done", "skipped_recent" or None when
    no refresh was asked — or the error dict the tool should return.
    """
    not_found = {"status": "error", "error_message": f"Character '{name}-{server}' ({region}) not found."}
    try:
        char = await resolve_character(name, server, region)
        if char is None:
            return not_found
        refresh = None
        if force_refresh:  # shared entry: one forced refresh per user per character per minute
            refresh = "done" if await try_claim_refresh(get_refresh_actor(), char.id) else "skipped_recent"
        query = (
            f"query Char{scope.title()}($id: Int!{var_decls}) {{ characterData {{ "
            f"character(id: $id) {{ name {field_call} }} }} }}"
        )

        async def load() -> CharacterRankings | None:
            data = await wcl_client.get_async_client().query(query, {"id": char.id, **variables})
            found = ((data.get("data") or {}).get("characterData") or {}).get("character")
            if not found:
                return None
            field = "zoneRankings" if scope == "zone" else "encounterRankings"
            return CharacterRankings(name=found.get("name") or char.name, scope=scope, rankings=found.get(field))

        ranked = await get_or_load(
            CacheFamily.CHAR_OVERVIEW, key_for(char.id), CharacterRankings, load,
            force_refresh=refresh == "done",
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    return (ranked, refresh) if ranked is not None else not_found


def _with_refresh(result: dict[str, Any], refresh: str | None) -> dict[str, Any]:
    if refresh is not None:
        result["refresh"] = refresh
    return result


async def get_character_zone_rankings(
    name: str, server: str, region: str, zone_id: int = 0, metric: str = "dps", difficulty: int = 0,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Get one player's parse percentiles across a whole raid zone.

    Args:
        name (str): Character name.
        server (str): Realm name (e.g. 'Stormrage'); slugified automatically.
        region (str): 'US', 'EU', 'KR', 'TW', 'CN'.
        zone_id (int): Raid zone id (0 = current/default zone).
        metric (str): 'dps', 'hps', etc.
        difficulty (int): Difficulty id (0 = default, e.g. 4=Heroic, 5=Mythic).
        force_refresh (bool): True only when the user explicitly asks to refresh or check
            again; bypasses the cached copy (at most once a minute per character).

    Returns:
        dict: {"status": "success", "zoneRankings": {...}} or an error. With
            force_refresh, "refresh" is "done" or "skipped_recent" (refreshed moments ago).
    """
    if metric not in METRICS:
        return {"status": "error", "error_message": f"Bad metric '{metric}'.", "valid": METRICS}
    # metric is inlined as a validated enum literal because zoneRankings and
    # encounterRankings expect different metric enum types.
    ranked = await _character_rankings(
        name, server, region, "zone",
        f"zoneRankings(zoneID: $zoneID, metric: {metric}, difficulty: $difficulty)",
        ", $zoneID: Int, $difficulty: Int",
        {"zoneID": zone_id or None, "difficulty": difficulty or None},
        lambda cid: keys.char_zone(cid, zone_id, metric, difficulty),
        force_refresh,
    )
    if isinstance(ranked, dict):
        return ranked
    ranked, refresh = ranked
    return with_envelope(
        _with_refresh(
            {"status": "success", "name": ranked.name, "zoneRankings": await _acap(ranked.rankings)}, refresh
        ),
        Provenance(metric=metric, difficulty=difficulty or None),
    )


async def get_character_encounter_rankings(
    name: str, server: str, region: str, encounter_id: int, metric: str = "dps", difficulty: int = 0,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Get one player's parse history on a single boss encounter.

    Args:
        name (str): Character name.
        server (str): Realm name; slugified automatically.
        region (str): 'US', 'EU', 'KR', 'TW', 'CN'.
        encounter_id (int): The boss encounter id.
        metric (str): 'dps', 'hps', etc.
        difficulty (int): Difficulty id (0 = default).
        force_refresh (bool): True only when the user explicitly asks to refresh or check
            again; bypasses the cached copy (at most once a minute per character).

    Returns:
        dict: {"status": "success", "encounterRankings": {...}} or an error. With
            force_refresh, "refresh" is "done" or "skipped_recent" (refreshed moments ago).
    """
    if metric not in METRICS:
        return {"status": "error", "error_message": f"Bad metric '{metric}'.", "valid": METRICS}
    ranked = await _character_rankings(
        name, server, region, "encounter",
        f"encounterRankings(encounterID: $encounterID, metric: {metric}, difficulty: $difficulty)",
        ", $encounterID: Int!, $difficulty: Int",
        {"encounterID": encounter_id, "difficulty": difficulty or None},
        lambda cid: keys.char_enc(cid, encounter_id, metric, difficulty),
        force_refresh,
    )
    if isinstance(ranked, dict):
        return ranked
    ranked, refresh = ranked
    return with_envelope(
        _with_refresh(
            {"status": "success", "name": ranked.name, "encounterRankings": await _acap(ranked.rankings)},
            refresh,
        ),
        Provenance(encounter_id=encounter_id, metric=metric, difficulty=difficulty or None),
    )


# --- Ultimate escape hatch ----------------------------------------------------

async def run_wcl_graphql(query: str, variables_json: str = "") -> dict[str, Any]:
    """Run an arbitrary read-only GraphQL query against the Warcraft Logs v2 API.

    Fallback for anything the other tools don't cover. You write the GraphQL. The
    schema root fields are: worldData (zones/encounters/regions), reportData
    (report(code:), reports(...)), characterData (character(...)), guildData
    (guild(...)), gameData (abilities/items/classes/factions), and rateLimitData.
    Fields like characterRankings, table, events, graph, zoneRankings return a
    JSON scalar (request them with no sub-selection). Endpoint is the public
    client API — private reports are not accessible.

    Args:
        query (str): A complete GraphQL query string.
        variables_json (str): JSON object of variables, or '' for none.

    Returns:
        dict: {"status": "success", "data": {...}} with the raw response, or an
            error (including GraphQL errors) so you can fix the query and retry.
    """
    try:
        variables = json.loads(variables_json) if variables_json.strip() else {}
    except json.JSONDecodeError as exc:
        return {"status": "error", "error_message": f"variables_json is not valid JSON: {exc}"}
    if not isinstance(variables, dict):
        return {"status": "error", "error_message": "variables_json must be a JSON object."}
    try:
        data = await wcl_client.get_async_client().query(query, variables)
    except Exception as exc:  # noqa: BLE001 - includes GraphQL errors for the model to fix
        return {"status": "error", "error_message": f"Query failed: {exc}"}
    return with_envelope({"status": "success", "data": await _acap(data.get("data"))}, Provenance())
