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
All return a ``dict`` with a ``"status"`` key.
"""

from __future__ import annotations

import json
from typing import Any

from .constants import METRICS
from .wcl_client import get_client

# --- Enum whitelists (inlined into queries after validation) ------------------
TABLE_DATA_TYPES = {
    "Summary", "DamageDone", "DamageTaken", "Healing", "Casts", "Deaths",
    "Debuffs", "Buffs", "Dispels", "Interrupts", "Resources", "Threat",
    "Survivability", "Resurrections",
}
EVENT_DATA_TYPES = {
    "All", "DamageDone", "DamageTaken", "Healing", "Casts", "Deaths", "Debuffs",
    "Buffs", "Dispels", "Interrupts", "Resources", "Threat", "Resurrections",
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


def _report_field(
    code: str,
    field_call: str,
    var_decls: str,
    variables: dict[str, Any],
    field_name: str,
) -> Any:
    """Run ``reportData.report(code:){ <field_call> }`` and return that field."""
    query = (
        f"query ReportQ($code: String!{var_decls}) {{ "
        f"reportData {{ report(code: $code) {{ {field_call} }} }} }}"
    )
    data = get_client().query(query, {"code": code, **variables})
    report = ((data.get("data") or {}).get("reportData") or {}).get("report")
    if report is None:
        return None
    return report.get(field_name)


def _fight_ids(fight_id: int) -> list[int] | None:
    """0 means 'all fights'; otherwise a single-fight filter list."""
    return [fight_id] if fight_id else None


# --- Report structure ---------------------------------------------------------

def get_report_fights(report_code: str) -> dict[str, Any]:
    """List the fights (pulls) in a Warcraft Logs report, with the players in each.

    Use this to turn a report code (e.g. from a leaderboard parse) into fight IDs
    and player source IDs, which the other report tools need. Report codes are the
    short string in a log URL: warcraftlogs.com/reports/<CODE>.

    Args:
        report_code (str): The report code.

    Returns:
        dict: {"status": "success", "title": ..., "zone": ...,
               "players": {id: {"name", "class"}},
               "fights": [{id, name, encounterID, difficulty, kill,
                           averageItemLevel, players:[names]}]} or an error.
    """
    query = """
    query ReportFights($code: String!) {
      reportData { report(code: $code) {
        title
        zone { id name }
        masterData { actors(type: "Player") { id name subType } }
        fights {
          id name encounterID difficulty kill
          startTime endTime fightPercentage averageItemLevel size friendlyPlayers
        }
      } }
    }
    """.strip()
    try:
        data = get_client().query(query, {"code": report_code})
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}

    report = ((data.get("data") or {}).get("reportData") or {}).get("report")
    if not report:
        return {"status": "error", "error_message": f"No report '{report_code}'."}

    actors = ((report.get("masterData") or {}).get("actors")) or []
    players = {a["id"]: {"name": a["name"], "class": a.get("subType")} for a in actors}
    fights = []
    for f in report.get("fights", []):
        names = [players[i]["name"] for i in (f.get("friendlyPlayers") or []) if i in players]
        fights.append(
            {
                "id": f["id"],
                "name": f["name"],
                "encounterID": f.get("encounterID"),
                "difficulty": f.get("difficulty"),
                "kill": f.get("kill"),
                "averageItemLevel": f.get("averageItemLevel"),
                "size": f.get("size"),
                "players": names,
            }
        )
    return {
        "status": "success",
        "title": report.get("title"),
        "zone": report.get("zone"),
        "players": players,
        "fights": _cap(fights),
    }


def get_report_master_data(report_code: str) -> dict[str, Any]:
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
        data = get_client().query(query, {"code": report_code})
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    md = (((data.get("data") or {}).get("reportData") or {}).get("report") or {}).get("masterData")
    if md is None:
        return {"status": "error", "error_message": f"No report '{report_code}'."}
    return {"status": "success", "actors": _cap(md.get("actors")), "abilities": _cap(md.get("abilities"))}


# --- The workhorses: table / events / graph -----------------------------------

def get_report_table(
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
            Survivability, Resurrections.
        fight_id (int): A single fight id (from get_report_fights). 0 = all fights.
        source_id (int): Filter to one actor id (0 = all). Use this to drill into
            one player's abilities.
        ability_id (int): Filter to one ability's game id (0 = all).
        hostility_type (str): 'Friendlies' (players) or 'Enemies' (NPCs/boss).

    Returns:
        dict: {"status": "success", "data_type": ..., "table": {...}} or an error.
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
        table = _report_field(report_code, field, var_decls, variables, "table")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if table is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return {"status": "success", "data_type": data_type, "table": _cap(table)}


def get_report_events(
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
            Resurrections, CombatantInfo, Summons.
        fight_id (int): Single fight id (0 = all).
        source_id (int): Actor id filter (0 = all).
        ability_id (int): Ability game id filter (0 = all).
        hostility_type (str): 'Friendlies' or 'Enemies'.
        limit (int): Max events per page (1-500).
        start_time (int): Report-relative ms to start from; pass the previous
            call's nextPageTimestamp to page forward. 0 = fight start.

    Returns:
        dict: {"status": "success", "events": {data:[...], nextPageTimestamp}} or error.
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
        events = _report_field(report_code, field, var_decls, variables, "events")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if events is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return {"status": "success", "data_type": data_type, "events": _cap(events)}


def get_report_graph(
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
        graph = _report_field(report_code, field, var_decls, variables, "graph")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if graph is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return {"status": "success", "data_type": data_type, "graph": _cap(graph)}


def get_report_rankings(report_code: str, fight_id: int = 0) -> dict[str, Any]:
    """Get the parse percentiles for the players in a report's fight(s).

    Args:
        report_code (str): The report code.
        fight_id (int): Single fight id (0 = all fights).

    Returns:
        dict: {"status": "success", "rankings": {...}} or an error.
    """
    field = "rankings(fightIDs: $fightIDs)"
    var_decls = ", $fightIDs: [Int]"
    try:
        rankings = _report_field(
            report_code, field, var_decls, {"fightIDs": _fight_ids(fight_id)}, "rankings"
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if rankings is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return {"status": "success", "rankings": _cap(rankings)}


def get_report_player_details(report_code: str, fight_id: int = 0) -> dict[str, Any]:
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
        details = _report_field(
            report_code, field, var_decls, {"fightIDs": _fight_ids(fight_id)}, "playerDetails"
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if details is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    return {"status": "success", "playerDetails": _cap(details)}


# --- Individual character history ---------------------------------------------

def _server_slug(server: str) -> str:
    return server.strip().lower().replace(" ", "-").replace("'", "")


def get_character_zone_rankings(
    name: str, server: str, region: str, zone_id: int = 0, metric: str = "dps", difficulty: int = 0
) -> dict[str, Any]:
    """Get one player's parse percentiles across a whole raid zone.

    Args:
        name (str): Character name.
        server (str): Realm name (e.g. 'Stormrage'); slugified automatically.
        region (str): 'US', 'EU', 'KR', 'TW', 'CN'.
        zone_id (int): Raid zone id (0 = current/default zone).
        metric (str): 'dps', 'hps', etc.
        difficulty (int): Difficulty id (0 = default, e.g. 4=Heroic, 5=Mythic).

    Returns:
        dict: {"status": "success", "zoneRankings": {...}} or an error.
    """
    if metric not in METRICS:
        return {"status": "error", "error_message": f"Bad metric '{metric}'.", "valid": METRICS}
    # metric is inlined as a validated enum literal because zoneRankings and
    # encounterRankings expect different metric enum types.
    query = f"""
    query CharZone($name: String!, $server: String!, $region: String!,
                   $zoneID: Int, $difficulty: Int) {{
      characterData {{ character(name: $name, serverSlug: $server, serverRegion: $region) {{
        name classID
        zoneRankings(zoneID: $zoneID, metric: {metric}, difficulty: $difficulty)
      }} }}
    }}
    """.strip()
    variables = {
        "name": name, "server": _server_slug(server), "region": region.upper(),
        "zoneID": zone_id or None, "difficulty": difficulty or None,
    }
    try:
        data = get_client().query(query, variables)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    char = ((data.get("data") or {}).get("characterData") or {}).get("character")
    if not char:
        return {"status": "error", "error_message": f"Character '{name}-{server}' ({region}) not found."}
    return {"status": "success", "name": char.get("name"), "zoneRankings": _cap(char.get("zoneRankings"))}


def get_character_encounter_rankings(
    name: str, server: str, region: str, encounter_id: int, metric: str = "dps", difficulty: int = 0
) -> dict[str, Any]:
    """Get one player's parse history on a single boss encounter.

    Args:
        name (str): Character name.
        server (str): Realm name; slugified automatically.
        region (str): 'US', 'EU', 'KR', 'TW', 'CN'.
        encounter_id (int): The boss encounter id.
        metric (str): 'dps', 'hps', etc.
        difficulty (int): Difficulty id (0 = default).

    Returns:
        dict: {"status": "success", "encounterRankings": {...}} or an error.
    """
    if metric not in METRICS:
        return {"status": "error", "error_message": f"Bad metric '{metric}'.", "valid": METRICS}
    query = f"""
    query CharEnc($name: String!, $server: String!, $region: String!,
                  $encounterID: Int!, $difficulty: Int) {{
      characterData {{ character(name: $name, serverSlug: $server, serverRegion: $region) {{
        name classID
        encounterRankings(encounterID: $encounterID, metric: {metric}, difficulty: $difficulty)
      }} }}
    }}
    """.strip()
    variables = {
        "name": name, "server": _server_slug(server), "region": region.upper(),
        "encounterID": encounter_id, "difficulty": difficulty or None,
    }
    try:
        data = get_client().query(query, variables)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    char = ((data.get("data") or {}).get("characterData") or {}).get("character")
    if not char:
        return {"status": "error", "error_message": f"Character '{name}-{server}' ({region}) not found."}
    return {"status": "success", "name": char.get("name"), "encounterRankings": _cap(char.get("encounterRankings"))}


# --- Ultimate escape hatch ----------------------------------------------------

def run_wcl_graphql(query: str, variables_json: str = "") -> dict[str, Any]:
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
        data = get_client().query(query, variables)
    except Exception as exc:  # noqa: BLE001 - includes GraphQL errors for the model to fix
        return {"status": "error", "error_message": f"Query failed: {exc}"}
    return {"status": "success", "data": _cap(data.get("data"))}
