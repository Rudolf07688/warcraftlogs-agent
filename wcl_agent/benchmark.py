"""``compare_player_to_cohort`` — a matched benchmark cohort (feature 009, US2).

Replaces "compare the player to the top parse" with a **matched cohort**: 3–5 kill
parses of the same encounter/difficulty/spec/metric/partition, from the ~75th–95th
percentile band located via ``totalParses`` (research R1), within ±15% of the
player's fight duration, aggregated as medians and ranges. The player's own rates
are per minute **alive** (FR-015a); cohort members' rates are per minute of their
fight. Budget-bounded (research R4). The heavy Casts tables are reduced in code and
never returned raw.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

from . import wcl_client
from .cache import keys
from .constants import METRICS
from .fight_time import PlayerResolutionError, fetch_dead_windows, resolve_player, windows_seconds
from .provenance import Completeness, PercentileContext, Provenance, flatten_report_rankings, with_envelope
from .queries import ENCOUNTER_RANKINGS
from .report_tools import _player_table, _report_field
from .aio import gather_settled, unwrap

BENCHMARK_METRICS = ("dps", "hps", "bossdps")
MAX_SIZE = 5
MAX_PAGE = 20  # WCL hard cap on characterRankings pages
BAND_LO, BAND_HI = 0.05, 0.25  # rank fractions ⇒ 75th–95th percentile
BAND_CENTRE = 0.15
DURATION_WINDOW_PCT = 15
DURATION_WINDOW_WIDE_PCT = 25
MIN_MATCHES = 3
TOP_ABILITIES_PER_ENTRY = 10
MAX_MEASURES = 20


# --- Pure helpers (unit-tested) -----------------------------------------------------


@dataclass(frozen=True)
class BandPages:
    pages: list[int]
    lo_rank: int
    hi_rank: int
    clipped: bool


def band_pages(total_parses: int | None) -> BandPages:
    """Leaderboard pages covering ranks ceil(5%·N)..floor(25%·N), ≤3, centred on 15%·N.

    Pages past 20 are unreachable (API cap) ⇒ pages 18–20 and ``clipped=True``.
    """
    n = int(total_parses or 0)
    if n < 100:
        return BandPages([1], 1, max(n, 1), False)
    lo = max(1, math.ceil(BAND_LO * n))
    hi = max(lo, math.floor(BAND_HI * n))
    lo_page, hi_page = math.ceil(lo / 100), math.ceil(hi / 100)
    centre = math.ceil(BAND_CENTRE * n / 100)
    first = max(lo_page, centre - 1)
    last = min(hi_page, first + 2)
    clipped = False
    if last > MAX_PAGE:
        clipped = True
        last = MAX_PAGE
        first = max(1, MAX_PAGE - 2)
    return BandPages(list(range(first, last + 1)), lo, hi, clipped)


@dataclass(frozen=True)
class CohortSelection:
    members: list[dict[str, Any]]
    window_pct: int
    widened: bool


def select_cohort(
    entries: list[dict[str, Any]],
    player_name: str,
    player_duration_ms: float,
    size: int,
) -> CohortSelection:
    """Nearest ``size`` entries by |Δduration| within ±15% (±25% if fewer than 3)."""
    own = (player_name or "").casefold()
    candidates = [
        e for e in entries
        if isinstance(e, dict) and e.get("duration") is not None
        and str(e.get("name", "")).casefold() != own
    ]

    def within(pct: int) -> list[dict[str, Any]]:
        tol = player_duration_ms * pct / 100
        return [e for e in candidates if abs(float(e["duration"]) - player_duration_ms) <= tol]

    window, widened = DURATION_WINDOW_PCT, False
    matched = within(window)
    if len(matched) < MIN_MATCHES:
        window, widened = DURATION_WINDOW_WIDE_PCT, True
        matched = within(window)
    matched.sort(key=lambda e: abs(float(e["duration"]) - player_duration_ms))
    return CohortSelection(matched[: max(0, size)], window, widened)


def cohort_label(size: int, unmet: list[str]) -> str:
    if size <= 1:
        return "anecdotal"
    if size < MIN_MATCHES or unmet:
        return "directional"
    return "matched"


def budget_size(requested: int, remaining_points: float | None) -> int:
    """Shrink the cohort when the hourly WCL budget is low (research R4)."""
    size = max(1, min(int(requested or 1), MAX_SIZE))
    if remaining_points is None:
        return size
    if remaining_points < 40:
        return 1
    if remaining_points < 100:
        return min(size, 3)
    return size


@dataclass(frozen=True)
class CastsEntry:
    name: str
    source_id: int | None
    class_spec: str | None  # from ``icon``, e.g. "Mage-Fire"
    item_level: float | None
    total: int
    abilities: list[dict[str, Any]] = field(default_factory=list)  # [{guid, name, total}] desc


def reduce_casts_entry(
    table: dict[str, Any] | None,
    name: str | None = None,
    source_id: int | None = None,
) -> CastsEntry | None:
    """Pick one player's entry out of an unfiltered Casts table and keep only what matters.

    ``source_id`` wins; else the first entry whose ``name`` matches (case-insensitive).
    ``activeTime`` is deliberately dropped (never an opportunity window).
    """
    entries = ((table or {}).get("data") or {}).get("entries") or []
    chosen = None
    for e in entries:
        if not isinstance(e, dict):
            continue
        if source_id is not None and e.get("id") == source_id:
            chosen = e
            break
        if source_id is None and name and str(e.get("name", "")).casefold() == name.casefold():
            chosen = e
            break
    if chosen is None:
        return None
    abilities = [
        {"guid": a.get("guid"), "name": a.get("name"), "total": int(a.get("total") or 0)}
        for a in (chosen.get("abilities") or [])
        if isinstance(a, dict)
    ]
    abilities.sort(key=lambda a: a["total"], reverse=True)
    return CastsEntry(
        name=str(chosen.get("name")),
        source_id=chosen.get("id"),
        class_spec=chosen.get("icon"),
        item_level=chosen.get("itemLevel"),
        total=int(chosen.get("total") or 0),
        abilities=abilities,
    )


def median_range(values: list[float]) -> dict[str, float] | None:
    """Median, quartiles and range of a sample (rounded to 2 dp); None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) > 1:
        p25, _, p75 = statistics.quantiles(ordered, n=4, method="inclusive")
    else:
        p25 = p75 = ordered[0]
    return {
        "median": round(statistics.median(ordered), 2),
        "p25": round(p25, 2),
        "p75": round(p75, 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
    }


def _per_min(total: int, minutes: float) -> float:
    return round(total / minutes, 2) if minutes > 0 else 0.0


def aggregate_measures(
    player: CastsEntry,
    player_minutes: float,
    members: list[tuple[CastsEntry, float]],
) -> list[dict[str, Any]]:
    """Casts/min per ability for the player vs the cohort (median, min, max, users).

    Abilities = union of the player's and each member's top abilities (≤20 kept,
    ordered by the player's rate then the cohort median).
    """
    keyed: dict[Any, dict[str, Any]] = {}
    for entry in [player, *[m for m, _ in members]]:
        for a in entry.abilities[:TOP_ABILITIES_PER_ENTRY]:
            key = a["guid"] if a["guid"] is not None else a["name"]
            keyed.setdefault(key, {"name": a["name"], "guid": a["guid"]})

    def _total(entry: CastsEntry, key: Any) -> int:
        for a in entry.abilities:
            if (a["guid"] if a["guid"] is not None else a["name"]) == key:
                return a["total"]
        return 0

    measures: list[dict[str, Any]] = []
    for key, ability in keyed.items():
        rates = [_per_min(_total(m, key), minutes) for m, minutes in members]
        users = sum(1 for m, _ in members if _total(m, key) > 0)
        spread = median_range(rates) or {}
        measures.append(
            {
                "ability": ability,
                "player_casts_per_min": _per_min(_total(player, key), player_minutes),
                "cohort_median_per_min": spread.get("median"),
                "cohort_min": spread.get("min"),
                "cohort_max": spread.get("max"),
                "cohort_users": users,
            }
        )
    measures.sort(
        key=lambda m: (m["player_casts_per_min"], m["cohort_median_per_min"] or 0), reverse=True
    )
    return measures[:MAX_MEASURES]


# --- The tool ---------------------------------------------------------------------


def report_link(code: str, fight_id: int | None = None) -> str:
    """Warcraft Logs URL for a report, or one fight in it (shared with the PDF report)."""
    url = f"https://www.warcraftlogs.com/reports/{code}"
    return f"{url}#fight={fight_id}" if fight_id is not None else url


def _player_block(resolved, row: PercentileContext | None, extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": resolved.name,
        "source_id": resolved.source_id,
        "class": (row.class_name if row else None) or resolved.class_name,
        "spec": row.spec if row else None,
        **extra,
    }


async def _fetch_report_context(report_code: str, fight_id: int, metric: str) -> dict[str, Any] | None:
    """masterData actors + the fight + report.rankings for that fight, in one call."""
    query = f"""
    query BenchmarkCtx($code: String!, $fightIDs: [Int]) {{
      reportData {{ report(code: $code) {{
        masterData {{ actors(type: "Player") {{ id name server subType }} }}
        fights(fightIDs: $fightIDs) {{
          id startTime endTime kill encounterID difficulty friendlyPlayers
        }}
        rankings(fightIDs: $fightIDs, playerMetric: {metric})
      }} }}
    }}
    """.strip()
    data = await wcl_client.get_async_client().query(
        query, {"code": report_code, "fightIDs": [fight_id]}
    )
    return ((data.get("data") or {}).get("reportData") or {}).get("report")


async def _casts_table(report_code: str, fight_id: int) -> dict[str, Any] | None:
    return await _report_field(
        report_code,
        "table(dataType: Casts, fightIDs: $fightIDs)",
        ", $fightIDs: [Int]",
        {"fightIDs": [fight_id]},
        "table",
    )


async def source_casts(report_code: str, fight_id: int, source_id: int) -> list[dict[str, Any]]:
    """Every ability one player cast in a fight (``[{guid, name, total}]``, most cast first).

    The source-filtered Casts table (cached per player, ``report_player``). Unlike the
    whole-raid table, which lists only each player's top few abilities, it includes the
    major cooldowns (feature 015).
    """
    table = await _player_table(
        report_code,
        "table(dataType: Casts, fightIDs: $fightIDs, sourceID: $sourceID)",
        ", $fightIDs: [Int], $sourceID: Int",
        {"fightIDs": [fight_id], "sourceID": source_id},
        keys.report_player(report_code, source_id, "Casts", fight_id, 0, "Friendlies"),
    )
    data = (table or {}).get("data") if isinstance((table or {}).get("data"), dict) else table
    abilities = [
        {"guid": e.get("guid"), "name": e.get("name"), "total": int(e.get("total") or 0)}
        for e in (data or {}).get("entries") or []
        if isinstance(e, dict) and e.get("guid") is not None
    ]
    abilities.sort(key=lambda a: a["total"], reverse=True)
    return abilities


async def compare_player_to_cohort(
    report_code: str,
    fight_id: int,
    player_name: str,
    metric: str = "dps",
    size: int = 5,
    source_id: int = 0,
) -> dict[str, Any]:
    """Benchmark one player's kill against a matched cohort of similar kill parses.

    Use this for "how do I compare", "why is my parse low", or "what should I do
    differently" questions about a specific pull. It returns a matched cohort of
    strong-but-not-extreme kill parses (same encounter, difficulty, spec, metric
    and partition as the player's pull, ~75th–95th percentile, fight duration
    within ±15%) with the median and range of casts per minute per ability and of
    throughput. Do NOT use get_rankings_distribution's top_parses as a benchmark —
    a single top parse is not representative.

    Player casts per minute are computed over time ALIVE (dead windows removed;
    see player.dead_s / alive_s). A death is itself a finding — report it before
    judging the rates. Cohort members' rates use their full fight duration.

    Args:
        report_code (str): The report code of the player's pull.
        fight_id (int): The fight id (must be a kill; a wipe returns status "limited").
        player_name (str): The player's character name as it appears in the report.
        metric (str): 'dps' (default), 'hps', or 'bossdps'.
        size (int): Cohort size, 1-5 (default 5); shrinks automatically when the WCL
            API budget is low.
        source_id (int): The player's source id, to disambiguate when two players
            share the name (an ambiguous name returns an error listing candidates).

    Returns:
        dict: {"status": "success", player, cohort: {size, requested_size, members,
            criteria, unmet_criteria, label: matched|directional|anecdotal},
            measures: [...], throughput: {...}, provenance, completeness};
            {"status": "limited", reason} for a wipe; or {"status": "error", ...}
            (with "candidates" when the name is ambiguous).
    """
    if metric not in METRICS or metric not in BENCHMARK_METRICS:
        return {"status": "error", "error_message": f"Bad metric '{metric}'.", "valid": list(BENCHMARK_METRICS)}
    if not fight_id or fight_id < 1:
        return {"status": "error", "error_message": "fight_id must be a single fight id (> 0)."}
    requested_size = max(1, min(int(size or MAX_SIZE), MAX_SIZE))

    try:
        report = await _fetch_report_context(report_code, fight_id, metric)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if not report or not report.get("fights"):
        return {"status": "error", "error_message": f"No fight {fight_id} in report '{report_code}'."}
    fight = report["fights"][0]
    actors = ((report.get("masterData") or {}).get("actors")) or []
    try:
        resolved = resolve_player(actors, fight.get("friendlyPlayers"), player_name, source_id)
    except PlayerResolutionError as exc:
        return exc.result

    fight_start, fight_end = float(fight.get("startTime") or 0), float(fight.get("endTime") or 0)
    duration_ms = max(0.0, fight_end - fight_start)
    provenance = Provenance(
        report_code=report_code,
        fight_id=fight_id,
        encounter_id=fight.get("encounterID"),
        difficulty=fight.get("difficulty"),
        metric=metric,
        source_id=resolved.source_id,
    )
    if not fight.get("kill"):
        return with_envelope(
            {
                "status": "limited",
                "reason": "wipe — no ranked population; any comparison is limited",
                "player": _player_block(resolved, None, {"duration_s": round(duration_ms / 1000, 1)}),
                "fight": {"kill": False, "duration_s": round(duration_ms / 1000, 1)},
            },
            provenance,
        )

    rows = flatten_report_rankings(
        report.get("rankings"), compare="Rankings", timeframe="Historical", metric=metric
    )
    row = next(
        (
            r for r in rows
            if (r.name or "").casefold() == resolved.name.casefold()
            and (not resolved.server or not r.server or r.server.casefold() == resolved.server.casefold())
        ),
        None,
    )
    if row is None:
        return {
            "status": "error",
            "error_message": f"'{resolved.name}' has no ranking row for fight {fight_id} (metric {metric}).",
            "ranked_players": sorted({r.name for r in rows if r.name}),
        }
    provenance.partition = row.partition
    provenance.encounter_id = row.encounter_id or provenance.encounter_id
    provenance.difficulty = row.difficulty or provenance.difficulty

    # PERF-002: after the report context, three independent branches run concurrently:
    # (1) budget + leaderboard pages → cohort → members' casts, (2) the player's casts,
    # (3) the player's death windows. Results are read back in the original order, so the
    # error precedence and messages are unchanged.
    band = band_pages(row.total_parses)

    async def leaderboard_page(page: int) -> list[dict[str, Any]]:
        data = await wcl_client.get_async_client().query(
            ENCOUNTER_RANKINGS,
            {
                "encounterID": row.encounter_id,
                "difficulty": row.difficulty,
                "metric": metric,
                "className": row.class_name,
                "specName": row.spec,
                "page": page,
                "partition": row.partition,
            },
        )
        blob = (((data.get("data") or {}).get("worldData") or {}).get("encounter") or {}).get(
            "characterRankings"
        ) or {}
        return blob.get("rankings") or []

    async def cohort_branch() -> dict[str, Any]:
        rl_res, *page_res = await gather_settled(
            wcl_client.acheck_rate_limit(), *(leaderboard_page(p) for p in band.pages)
        )
        # Budget → size (research R4). Budget unknown ⇒ no shrink.
        remaining: float | None = None
        if not isinstance(rl_res, BaseException):
            try:
                remaining = float(rl_res["limitPerHour"]) - float(rl_res["pointsSpentThisHour"])
            except Exception:  # noqa: BLE001
                remaining = None
        size_now = budget_size(requested_size, remaining)
        out: dict[str, Any] = {"remaining": remaining, "size_now": size_now}
        # Band pages (research R1), appended in page order (select_cohort depends on it).
        entries: list[dict[str, Any]] = []
        for res in page_res:
            if isinstance(res, BaseException):
                out["page_error"] = res
                return out
            entries.extend(res)
        selection = select_cohort(entries, resolved.name, duration_ms, size_now)
        out["selection"] = selection
        # Members' casts tables, concurrently; one member failing must not sink the benchmark.
        fetchable = [
            e for e in selection.members
            if (e.get("report") or {}).get("code") and (e.get("report") or {}).get("fightID")
        ]
        casts = await gather_settled(
            *(_casts_table(e["report"]["code"], int(e["report"]["fightID"])) for e in fetchable)
        )
        out["member_casts"] = {id(e): c for e, c in zip(fetchable, casts)}
        return out

    cohort_res, casts_res, dead_res = await gather_settled(
        cohort_branch(),
        _casts_table(report_code, fight_id),
        fetch_dead_windows(report_code, fight_id, resolved.source_id, fight_end),
    )
    if isinstance(cohort_res, BaseException):  # an unexpected failure outside the WCL calls
        return {"status": "error", "error_message": f"WCL request failed (leaderboard): {cohort_res}"}

    remaining = cohort_res["remaining"]
    size_now = cohort_res["size_now"]
    unmet: list[str] = []
    if size_now < requested_size:
        unmet.append(f"WCL budget low ({remaining:.0f} points left): cohort shrunk to {size_now}")
    if row.total_parses is None:
        unmet.append("population size unknown; sampled the top leaderboard page")
    if band.clipped:
        unmet.append("band clipped: the 75th–95th percentile band lies beyond page 20; sampled pages 18–20")
    if "page_error" in cohort_res:
        return {"status": "error", "error_message": f"WCL request failed (leaderboard): {cohort_res['page_error']}"}

    selection = cohort_res["selection"]
    if selection.widened:
        unmet.append(f"duration window widened to ±{selection.window_pct}%")
    if len(selection.members) < size_now:
        unmet.append(f"only {len(selection.members)} parses within ±{selection.window_pct}% duration")

    # Player's own casts (entry by source id) and time alive (FR-015a).
    try:
        player_entry = reduce_casts_entry(unwrap(casts_res), source_id=resolved.source_id)
        dead = unwrap(dead_res)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed (player casts): {exc}"}
    dead_s = windows_seconds([(max(s, fight_start), min(e, fight_end)) for s, e in dead])
    alive_s = max(1.0, round(duration_ms / 1000 - dead_s, 1))

    # Members' casts (entry by name), rates per minute of their own fight.
    members_out: list[dict[str, Any]] = []
    member_entries: list[tuple[CastsEntry, float]] = []
    member_casts = cohort_res["member_casts"]
    for e in selection.members:
        rep = e.get("report") or {}
        code, fid = rep.get("code"), rep.get("fightID")
        m_duration_s = float(e["duration"]) / 1000
        server = e.get("server") or {}
        members_out.append(
            {
                "name": e.get("name"),
                "server": server.get("name") if isinstance(server, dict) else server,
                "amount": e.get("amount"),
                "duration_s": round(m_duration_s, 1),
                "item_level": e.get("bracketData"),
                "report_code": code,
                "fight_id": fid,
                "link": report_link(code, fid) if code and fid else None,
            }
        )
        if not code or not fid:
            continue
        try:
            entry = reduce_casts_entry(unwrap(member_casts[id(e)]), name=e.get("name"))
        except Exception:  # noqa: BLE001 - one member failing must not sink the benchmark
            entry = None
        if entry is not None:
            member_entries.append((entry, m_duration_s / 60))
    if len(member_entries) < len(selection.members):
        unmet.append(f"casts available for {len(member_entries)} of {len(selection.members)} members")

    cohort_size = len(selection.members)
    label = cohort_label(cohort_size, unmet)
    amounts = [float(e.get("amount") or 0) for e in selection.members]
    measures = (
        aggregate_measures(player_entry, alive_s / 60, member_entries) if player_entry else []
    )
    result = {
        "status": "success",
        "player": _player_block(
            resolved,
            row,
            {
                "amount": row.amount,
                "duration_s": round(duration_ms / 1000, 1),
                "item_level": row.item_level,
                "dead_s": dead_s,
                "alive_s": alive_s,
                "rate_basis": "alive_time",
                "percentile": asdict(row),
                "link": report_link(report_code, fight_id),
            },
        ),
        "cohort": {
            "size": cohort_size,
            "requested_size": requested_size,
            "members": members_out,
            "criteria": {
                "encounter_id": row.encounter_id,
                "difficulty": row.difficulty,
                "class": row.class_name,
                "spec": row.spec,
                "metric": metric,
                "partition": row.partition,
                "kill_only": True,
                "duration_window_pct": selection.window_pct,
                "percentile_band": [75, 95],
                "band_sampled": _band_sampled(band, row.total_parses),
                "rate_basis": "fight_duration",
            },
            "unmet_criteria": unmet,
            "label": label,
        },
        "measures": measures,
        "throughput": {
            "metric": metric,
            "player_amount": row.amount,
            "cohort_median": round(statistics.median(amounts), 1) if amounts else None,
            "cohort_min": round(min(amounts), 1) if amounts else None,
            "cohort_max": round(max(amounts), 1) if amounts else None,
        },
    }
    return with_envelope(
        result,
        provenance,
        Completeness(
            sample_size=cohort_size,
            sample_scope="band_clipped" if band.clipped else "full",
        ),
    )


def _band_sampled(band: BandPages, total_parses: int | None) -> list[float] | None:
    """Approximate percentile range actually sampled: 100 − 100·rank/N."""
    if not total_parses:
        return None
    first_rank = (band.pages[0] - 1) * 100 + 1
    last_rank = min(band.pages[-1] * 100, total_parses)
    return [round(100 - 100 * last_rank / total_parses, 1), round(100 - 100 * first_rank / total_parses, 1)]
