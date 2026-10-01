"""ADK function-tools the agent calls to fetch and analyze WCL rankings.

Each tool returns a plain ``dict`` with a ``"status"`` key (``"success"`` or
``"error"``) so the model can react to failures and retry. The currently
selected encounter is read from the ADK session state via ``ToolContext`` — it
was placed there from the startup menu (see ``main.py``).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from google.adk.tools import ToolContext

from .constants import CLASS_SPECS, METRICS, normalize_class_name
from .queries import ENCOUNTER_RANKINGS, MENU_DISCOVERY
from .wcl_client import check_rate_limit as _check_rate_limit
from .wcl_client import get_client

MAX_PAGES = 10  # hard cap to protect the API points budget

_DIFFICULTY_NAMES = {5: "Mythic", 4: "Heroic", 3: "Normal", 1: "LFR"}


def _selection(tool_context: ToolContext) -> dict[str, Any]:
    """Pull the encounter selection out of session state."""
    state = tool_context.state
    return {
        "encounterID": state.get("encounterID"),
        "encounterName": state.get("encounterName"),
        "difficultyID": state.get("difficultyID"),
        "difficultyName": state.get("difficultyName"),
        "partition": state.get("partition"),
    }


def _fetch_rankings(
    sel: dict[str, Any],
    metric: str,
    class_name: str | None,
    spec_name: str | None,
    num_pages: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Page ``characterRankings``; return (entries, more_pages_available).

    The leaderboard is sorted by score descending, so the fetched entries are
    the top ``num_pages * 100`` parses. ``more_pages_available`` is True when
    lower-ranked parses remain beyond what was fetched.
    """
    client = get_client()
    entries: list[dict[str, Any]] = []
    has_more = False
    for page in range(1, num_pages + 1):
        variables = {
            "encounterID": sel["encounterID"],
            "difficulty": sel["difficultyID"],
            "metric": metric,
            "className": class_name,
            "specName": spec_name,
            "page": page,
            "partition": sel["partition"],
        }
        data = client.query(ENCOUNTER_RANKINGS, variables)
        blob = data["data"]["worldData"]["encounter"]["characterRankings"] or {}
        entries.extend(blob.get("rankings", []))
        has_more = bool(blob.get("hasMorePages"))
        if not has_more:
            break
    return entries, has_more


def _summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute percentile stats + spec breakdown for a list of ranking entries."""
    df = pd.DataFrame(entries)
    if df.empty or "amount" not in df.columns:
        return {"sample_size": 0}

    amounts = pd.to_numeric(df["amount"], errors="coerce").dropna()
    qs = amounts.quantile([0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0])
    percentiles = {
        "min": round(float(qs[0.0]), 1),
        "p25": round(float(qs[0.25]), 1),
        "median": round(float(qs[0.5]), 1),
        "p75": round(float(qs[0.75]), 1),
        "p90": round(float(qs[0.9]), 1),
        "p95": round(float(qs[0.95]), 1),
        "p99": round(float(qs[0.99]), 1),
        "max": round(float(qs[1.0]), 1),
    }

    spec_breakdown: list[dict[str, Any]] = []
    if "spec" in df.columns:
        grouped = df.groupby("spec")["amount"].agg(["count", "median", "max"])
        grouped = grouped.sort_values("median", ascending=False)
        for spec, row in grouped.iterrows():
            spec_breakdown.append(
                {
                    "spec": spec,
                    "count": int(row["count"]),
                    "median_amount": round(float(row["median"]), 1),
                    "max_amount": round(float(row["max"]), 1),
                }
            )

    top_parses = []
    for entry in sorted(entries, key=lambda e: e.get("amount", 0), reverse=True)[:5]:
        server = entry.get("server") or {}
        report = entry.get("report") or {}
        top_parses.append(
            {
                "name": entry.get("name"),
                "spec": entry.get("spec"),
                "server": server.get("name"),
                "region": server.get("region"),
                "amount": round(float(entry.get("amount", 0)), 1),
                "item_level": entry.get("bracketData"),
                "report_code": report.get("code"),
                "fight_id": report.get("fightID"),
            }
        )

    return {
        "sample_size": int(len(df)),
        "amount_percentiles": percentiles,
        "spec_breakdown": spec_breakdown,
        "top_parses": top_parses,
    }


def get_selected_encounter(tool_context: ToolContext) -> dict[str, Any]:
    """Return the encounter, difficulty, and season the user chose at startup.

    Call this first to confirm what you are analyzing before fetching rankings.

    Returns:
        dict: {"status": "success", "selection": {...}} with the encounter name,
            difficulty name, and partition (season) id.
    """
    sel = _selection(tool_context)
    if not sel.get("encounterID"):
        return {
            "status": "error",
            "error_message": (
                "No encounter is selected in this session. Use find_encounter to "
                "resolve the boss/difficulty the user asked about, then pass its "
                "encounter_id and difficulty_id to the ranking tools."
            ),
        }
    return {"status": "success", "selection": sel}


def find_encounter(query: str) -> dict[str, Any]:
    """Resolve a raid boss/encounter by name to its id, zone, and difficulties.

    Use this when no encounter is pre-selected (e.g. the web app) to turn a name
    like "Ula'tek" or "heroic ulatek" into the encounter_id and difficulty_id that
    get_rankings_distribution / compare_specs need.

    Args:
        query (str): A boss/encounter name (partial, any casing), e.g. 'ulatek'.

    Returns:
        dict: {"status": "success", "matches": [ {encounter_id, encounter, zone,
            zone_id, difficulties:[{id,name}], default_partition} ]} or an error.
    """
    try:
        data = get_client().query(MENU_DISCOVERY)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}

    q = query.strip().lower().replace("'", "")
    for word in ("mythic", "heroic", "normal", "lfr"):
        q = q.replace(word, "")
    q = q.strip()

    matches: list[dict[str, Any]] = []
    for zone in data["data"]["worldData"]["zones"]:
        for enc in zone.get("encounters") or []:
            name = enc["name"].lower().replace("'", "")
            if q and q in name:
                matches.append(
                    {
                        "encounter_id": enc["id"],
                        "encounter": enc["name"],
                        "zone": zone["name"],
                        "zone_id": zone["id"],
                        "difficulties": [
                            {"id": d["id"], "name": d["name"]}
                            for d in (zone.get("difficulties") or [])
                        ],
                        "default_partition": next(
                            (p["id"] for p in (zone.get("partitions") or []) if p.get("default")),
                            None,
                        ),
                    }
                )
    if not matches:
        return {"status": "error", "error_message": f"No encounter matching '{query}'."}
    return {"status": "success", "matches": matches[:8]}


def get_spec_options(class_name: str) -> dict[str, Any]:
    """List the valid API spec-filter values for a WoW class.

    Warcraft Logs expects PascalCase, space-free class/spec names (e.g.
    'Hunter' with specs 'BeastMastery', 'Marksmanship', 'Survival'). Use this to
    get the exact strings to pass to get_rankings_distribution / compare_specs.

    Args:
        class_name (str): A class name in any casing/spacing (e.g. 'hunter',
            'Death Knight').

    Returns:
        dict: {"status": "success", "class_name": <filter value>,
               "specs": [...]} or an error with the list of valid classes.
    """
    normalized = normalize_class_name(class_name)
    if not normalized:
        return {
            "status": "error",
            "error_message": f"Unknown class '{class_name}'.",
            "valid_classes": list(CLASS_SPECS.keys()),
        }
    return {
        "status": "success",
        "class_name": normalized,
        "display": CLASS_SPECS[normalized]["display"],
        "specs": CLASS_SPECS[normalized]["specs"],
    }


def get_rankings_distribution(
    class_name: str,
    spec_name: str,
    metric: str,
    num_pages: int,
    tool_context: ToolContext,
    encounter_id: int = 0,
    difficulty_id: int = 0,
) -> dict[str, Any]:
    """Fetch current-season ranking scores for a class/spec and summarize them.

    Pulls the leaderboard for the given (or session-selected) encounter+difficulty
    and computes the score (amount) percentile distribution, a per-spec breakdown,
    and the top parses. Scores are sorted highest-first, so a bounded page pull
    characterizes the top of the current-season distribution.

    Args:
        class_name (str): API class filter, e.g. 'Hunter'. Pass '' for all classes.
        spec_name (str): API spec filter, e.g. 'Marksmanship'. Pass '' for all
            specs of the class (or all specs if class is also '').
        metric (str): Ranking metric: 'dps', 'hps', 'wdps', or 'default'.
        num_pages (int): How many 100-entry pages to pull (1-10). More pages =
            deeper distribution but higher API cost. Use 3-5 for a good overview.
        encounter_id (int): Encounter to analyze. 0 = use the session's selected
            encounter. When nothing is pre-selected (web app), resolve it first with
            find_encounter and pass the id here.
        difficulty_id (int): 5=Mythic, 4=Heroic, 3=Normal, 1=LFR. 0 = use the
            session's difficulty (defaults to Heroic if none).

    Returns:
        dict: {"status": "success", ...summary...} including sample_size,
            amount_percentiles, spec_breakdown, and top_parses; or an error.
    """
    sel = _selection(tool_context)
    if encounter_id:
        diff = difficulty_id or sel.get("difficultyID") or 4
        sel = {
            "encounterID": encounter_id,
            "encounterName": sel.get("encounterName") or f"encounter {encounter_id}",
            "difficultyID": diff,
            "difficultyName": _DIFFICULTY_NAMES.get(diff, str(diff)),
            "partition": sel.get("partition"),
        }
    elif difficulty_id and sel.get("encounterID"):
        sel = {
            **sel,
            "difficultyID": difficulty_id,
            "difficultyName": _DIFFICULTY_NAMES.get(difficulty_id, sel.get("difficultyName")),
        }
    if not sel.get("encounterID"):
        return {
            "status": "error",
            "error_message": (
                "No encounter selected. Call find_encounter to resolve the boss and "
                "difficulty, then pass encounter_id (and difficulty_id)."
            ),
        }
    if metric not in METRICS:
        return {
            "status": "error",
            "error_message": f"Unsupported metric '{metric}'.",
            "valid_metrics": METRICS,
        }

    pages = max(1, min(int(num_pages or 1), MAX_PAGES))
    try:
        entries, has_more = _fetch_rankings(
            sel,
            metric=metric,
            class_name=class_name or None,
            spec_name=spec_name or None,
            num_pages=pages,
        )
    except Exception as exc:  # noqa: BLE001 - surface any API failure to the model
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}

    summary = _summarize(entries)
    if summary.get("sample_size", 0) == 0:
        return {
            "status": "success",
            "note": "No ranking entries found for these filters.",
            "encounter": sel["encounterName"],
            "difficulty": sel["difficultyName"],
            "filters": {"class": class_name, "spec": spec_name, "metric": metric},
            **summary,
        }

    return {
        "status": "success",
        "encounter": sel["encounterName"],
        "difficulty": sel["difficultyName"],
        "season_partition": sel["partition"],
        "filters": {"class": class_name, "spec": spec_name, "metric": metric},
        "pages_fetched": pages,
        "more_pages_available": has_more,
        "sample_note": (
            "Percentiles are computed over the fetched sample of {n} parses, "
            "which are the TOP scorers (leaderboard sorted by score descending)."
            + (" More lower-ranked parses exist; fetch more pages to reach "
               "lower percentiles." if has_more else "")
        ).format(n=summary.get("sample_size", 0)),
        **summary,
    }


def compare_specs(
    class_name: str,
    metric: str,
    num_pages: int,
    tool_context: ToolContext,
    encounter_id: int = 0,
    difficulty_id: int = 0,
) -> dict[str, Any]:
    """Compare every spec of a class on the given encounter side-by-side.

    Runs get_rankings_distribution for each spec of the class and returns their
    median/max/p95 scores together, ranked by median.

    Args:
        class_name (str): Class name in any casing (e.g. 'hunter').
        metric (str): Ranking metric: 'dps', 'hps', 'wdps', or 'default'.
        num_pages (int): Pages per spec (1-10). Keep small (1-3) since this makes
            one request set per spec.
        encounter_id (int): Encounter to analyze. 0 = session's selected encounter
            (resolve with find_encounter first in the web app).
        difficulty_id (int): 5=Mythic, 4=Heroic, 3=Normal, 1=LFR. 0 = session default.

    Returns:
        dict: {"status": "success", "comparison": [ {spec, sample_size,
            median, p95, max}, ... ]} ranked by median score, or an error.
    """
    normalized = normalize_class_name(class_name)
    if not normalized:
        return {
            "status": "error",
            "error_message": f"Unknown class '{class_name}'.",
            "valid_classes": list(CLASS_SPECS.keys()),
        }

    comparison = []
    for spec in CLASS_SPECS[normalized]["specs"]:
        result = get_rankings_distribution(
            class_name=normalized,
            spec_name=spec,
            metric=metric,
            num_pages=num_pages,
            tool_context=tool_context,
            encounter_id=encounter_id,
            difficulty_id=difficulty_id,
        )
        if result.get("status") != "success" or result.get("sample_size", 0) == 0:
            comparison.append({"spec": spec, "sample_size": 0})
            continue
        pcts = result.get("amount_percentiles", {})
        comparison.append(
            {
                "spec": spec,
                "sample_size": result.get("sample_size"),
                "median": pcts.get("median"),
                "p95": pcts.get("p95"),
                "max": pcts.get("max"),
            }
        )

    comparison.sort(key=lambda c: (c.get("median") or 0), reverse=True)
    return {
        "status": "success",
        "class_name": normalized,
        "metric": metric,
        "comparison": comparison,
    }


def check_rate_limit() -> dict[str, Any]:
    """Report the remaining Warcraft Logs API points for this hour.

    Returns:
        dict: {"status": "success", "limitPerHour": ..., "pointsSpentThisHour":
            ..., "pointsRemaining": ..., "pointsResetIn": ...} or an error.
    """
    try:
        rl = _check_rate_limit()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    remaining = rl["limitPerHour"] - rl["pointsSpentThisHour"]
    return {
        "status": "success",
        "limitPerHour": rl["limitPerHour"],
        "pointsSpentThisHour": rl["pointsSpentThisHour"],
        "pointsRemaining": round(remaining, 1),
        "pointsResetIn": rl["pointsResetIn"],
    }
