"""Stage 2: the measured Warcraft Logs data sheet for one spec and content type.

What top players of this spec actually do this patch/season (FR-032..FR-035, research
R5/R6): from logs-only top rankings (with talents and gear), a capped cohort's casts per
minute, the shortest gaps between casts of major cooldowns, buff/debuff uptimes and
secondary stats. Ability ids in the coaching brief come only from here (FR-034). Built in
the background lane and cached 12 h per patch or season; a thin sample is kept but marked
insufficient, so it is never stated as guidance (FR-033).
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from wcl_agent.client import wcl_client
from wcl_agent.client.aio import gather_settled
from wcl_agent.tools.benchmark import CastsEntry, median_range, source_casts
from wcl_agent.cache.cache import CacheFamily, get_or_load, keys
from wcl_agent.cache.cache_models import DataSheetCache, TalentNames
from wcl_agent.menu import load_world_zones
from wcl_agent.game.patch import (
    HEROIC_DIFFICULTY_ID,
    MYTHIC_PLUS_DIFFICULTY_ID,
    mplus_zone_from,
    raid_zone_from,
)
from wcl_agent.client.queries import SPEC_RANKINGS
from wcl_agent.tools.report_tools import _player_table, _report_field, load_report_summary
from wcl_agent.client.wcl_client import background_lane

from ...config import settings
from .models import (
    DataSheet,
    GenerationBriefing,
    ObservedAbility,
    ObservedBuild,
    ObservedStat,
    ObservedUptime,
    SampleScope,
    TalentPick,
    TalentRef,
)

logger = logging.getLogger(__name__)

MYTHIC_DIFFICULTY_ID = 5
ENCOUNTERS = 4  # encounters sampled per sheet (research R6)
MIN_RANKINGS = 50  # ranking entries needed before the sample counts
GAP_PLAYERS = 5  # players whose cast events give the shortest gaps
DETAIL_PLAYERS = 10  # players whose uptimes and stats are read
MIN_COOLDOWN_GAP_S = 20.0  # shorter gaps are rotational spells, not cooldowns
MAX_ABILITIES = 20
MAX_UPTIMES = 12
MAX_TALENTS = 40
ALWAYS_ON_PCT = 99.5  # raid buffs and passives: no coaching value in an uptime
# QA PERF-001: share of the hourly WCL budget kept for interactive chat lookups. Below it,
# a data sheet is postponed (the run fails "wcl_budget" and is retried on a later scan).
CHAT_RESERVE_SHARE = 0.4


class WclBudgetLow(Exception):
    """Too little of the hourly WCL budget is left to build a data sheet without starving chat."""
_STATS = ("Crit", "Haste", "Mastery", "Versatility", "Leech", "Avoidance", "Speed")


# --- pure reducers (unit-tested) ---------------------------------------------------------


def cohort_from(entries_by_encounter: list[list[dict]], size: int) -> list[dict]:
    """Up to ``size`` ranking entries with a report, one per player name, taken round-robin
    over the encounters so no single boss dominates."""
    chosen: list[dict] = []
    seen: set[str] = set()
    queues = [[e for e in entries if (e.get("report") or {}).get("code")] for entries in entries_by_encounter]
    while len(chosen) < size and any(queues):
        for queue in queues:
            while queue:
                entry = queue.pop(0)
                name = str(entry.get("name") or "").casefold()
                if name and name not in seen:
                    seen.add(name)
                    chosen.append(entry)
                    break
            if len(chosen) >= size:
                break
    return chosen


def talent_hash(talents: list[dict]) -> str:
    canonical = ",".join(
        f"{t.get('talentID')}:{t.get('points', 1)}"
        for t in sorted(talents, key=lambda t: int(t.get("talentID") or 0))
    )
    return hashlib.sha1(canonical.encode()).hexdigest()[:10]


def talent_summary(
    entries: list[dict], names: dict[int, str] | None = None
) -> tuple[list[ObservedBuild], list[TalentPick]]:
    """Build shares (by exact talent set) and per-talent pick rates over ranking entries."""
    names = names or {}
    with_talents = [e for e in entries if e.get("talents")]
    if not with_talents:
        return [], []
    total = len(with_talents)
    picks: Counter[int] = Counter()
    builds: Counter[str] = Counter()
    build_talents: dict[str, set[int]] = {}
    for entry in with_talents:
        ids = {int(t["talentID"]) for t in entry["talents"] if t.get("talentID")}
        picks.update(ids)
        h = talent_hash(entry["talents"])
        builds[h] += 1
        build_talents[h] = ids
    pick_pct = {tid: round(100 * n / total, 1) for tid, n in picks.items()}
    rates = [
        TalentPick(talent_id=tid, name=names.get(tid), pick_pct=pct)
        for tid, pct in sorted(pick_pct.items(), key=lambda kv: (-kv[1], kv[0]))
    ][:MAX_TALENTS]
    top = []
    for h, n in builds.most_common(3):
        # Notable = talents this build takes that most top players do not take.
        notable = sorted((tid for tid in build_talents[h] if pick_pct[tid] < 90), key=lambda t: pick_pct[t])[:8]
        top.append(
            ObservedBuild(
                talent_ids_hash=h,
                share_pct=round(100 * n / total, 1),
                players=n,
                notable_talents=[TalentRef(talent_id=t, name=names.get(t)) for t in notable],
            )
        )
    return top, rates


def ability_stats(members: list[tuple[Any, float]], gaps: dict[int, float]) -> list[ObservedAbility]:
    """Casts-per-minute spread per ability over the cohort (``members`` = (CastsEntry, minutes))."""
    if not members:
        return []
    names: dict[int, str] = {}
    totals: dict[int, list[float]] = defaultdict(list)
    for entry, minutes in members:
        seen = set()
        for a in entry.abilities:
            guid = a.get("guid")
            if guid is None or minutes <= 0 or guid in seen:
                continue
            seen.add(guid)
            names[guid] = a.get("name") or str(guid)
            totals[guid].append(a["total"] / minutes)
    minimum_users = max(2, len(members) // 4)
    out = []
    for guid, rates in totals.items():
        if len(rates) < minimum_users:
            continue
        # Players who never cast it count as zero, so the median is per cohort member.
        spread = median_range(rates + [0.0] * (len(members) - len(rates))) or {}
        out.append(
            ObservedAbility(
                ability_id=int(guid),
                name=names[guid],
                casts_per_min_median=spread.get("median"),
                casts_per_min_p25=spread.get("p25"),
                casts_per_min_p75=spread.get("p75"),
                min_gap_s=gaps.get(int(guid)),
                players_using=len(rates),
            )
        )
    out.sort(key=lambda a: (-(a.players_using), -(a.casts_per_min_median or 0)))
    return out[:MAX_ABILITIES]


def shortest_gaps(events: list[dict]) -> dict[int, float]:
    """Per ability, the shortest time between two casts (s), kept when ≥ 20 s (cooldowns)."""
    times: dict[int, list[float]] = defaultdict(list)
    for e in events:
        if e.get("type") == "cast" and e.get("abilityGameID") is not None:
            times[int(e["abilityGameID"])].append(float(e.get("timestamp") or 0))
    gaps: dict[int, float] = {}
    for guid, stamps in times.items():
        stamps.sort()
        diffs = [(b - a) / 1000 for a, b in zip(stamps, stamps[1:]) if b > a]
        if diffs and min(diffs) >= MIN_COOLDOWN_GAP_S:
            gaps[guid] = round(min(diffs), 1)
    return gaps


def merge_gaps(per_player: list[dict[int, float]]) -> dict[int, float]:
    """The shortest gap any sampled player achieved: a lower bound on the cooldown."""
    merged: dict[int, float] = {}
    for gaps in per_player:
        for guid, gap in gaps.items():
            merged[guid] = min(gap, merged.get(guid, gap))
    return merged


def uptime_stats(tables: list[tuple[str, dict]], cohort: int) -> list[ObservedUptime]:
    """Median uptime % per aura over the players whose tables were read."""
    pct: dict[tuple[str, int], list[float]] = defaultdict(list)
    names: dict[int, str] = {}
    for kind, table in tables:
        data = table.get("data") if isinstance(table.get("data"), dict) else table
        total = float(data.get("totalTime") or 0)
        if total <= 0:
            continue
        for aura in data.get("auras") or []:
            guid = aura.get("guid")
            if guid is None:
                continue
            names[int(guid)] = aura.get("name") or str(guid)
            pct[(kind, int(guid))].append(min(100.0, 100 * float(aura.get("totalUptime") or 0) / total))
    minimum = max(2, cohort // 2)
    out = [
        ObservedUptime(
            ability_id=guid,
            name=names[guid],
            kind=kind,  # type: ignore[arg-type]
            uptime_pct_median=(median_range(values) or {}).get("median", 0.0),
            players=len(values),
        )
        for (kind, guid), values in pct.items()
        if len(values) >= minimum
    ]
    out = [u for u in out if u.uptime_pct_median < ALWAYS_ON_PCT]
    out.sort(key=lambda u: (-u.players, -u.uptime_pct_median))
    return out[:MAX_UPTIMES]


def stat_spread(details: list[dict]) -> list[ObservedStat]:
    """Secondary-stat ratings from ``combatantInfo.stats`` (the ``min`` value is the rating)."""
    values: dict[str, list[float]] = defaultdict(list)
    for player in details:
        stats = ((player.get("combatantInfo") or {}).get("stats")) or {}
        for name in _STATS:
            raw = stats.get(name)
            rating = raw.get("min") if isinstance(raw, dict) else raw
            if isinstance(rating, (int, float)) and rating > 0:
                values[name].append(float(rating))
    out = []
    for name in _STATS:
        spread = median_range(values.get(name, []))
        if spread:
            out.append(ObservedStat(stat=name, median_rating=spread["median"], p25=spread["p25"], p75=spread["p75"]))
    return out


# --- Warcraft Logs lookups ---------------------------------------------------------------


async def _rankings(encounter_id: int, briefing: GenerationBriefing, metric: str, difficulty: int) -> list[dict]:
    data = await wcl_client.get_async_client().query(
        SPEC_RANKINGS,
        {
            "encounterID": encounter_id,
            "className": briefing.class_name,
            "specName": briefing.spec,
            "metric": metric,
            "difficulty": difficulty,
            "page": 1,
        },
    )
    blob = (((data.get("data") or {}).get("worldData") or {}).get("encounter") or {}).get("characterRankings") or {}
    return [e for e in blob.get("rankings") or [] if isinstance(e, dict)]


async def _events(code: str, fight_id: int, source_id: int) -> list[dict]:
    events = await _report_field(
        code,
        "events(fightIDs: $fightIDs, dataType: Casts, sourceID: $sourceID, limit: 10000) { data nextPageTimestamp }",
        ", $fightIDs: [Int], $sourceID: Int",
        {"fightIDs": [fight_id], "sourceID": source_id},
        "events",
    )
    return list((events or {}).get("data") or [])


async def _aura_table(code: str, fight_id: int, source_id: int, kind: str) -> dict | None:
    data_type, hostility = ("Buffs", "Friendlies") if kind == "buff" else ("Debuffs", "Enemies")
    field = (
        f"table(dataType: {data_type}, hostilityType: {hostility}, fightIDs: $fightIDs, sourceID: $sourceID)"
    )
    return await _player_table(
        code,
        field,
        ", $fightIDs: [Int], $sourceID: Int",
        {"fightIDs": [fight_id], "sourceID": source_id},
        keys.report_player(code, source_id, data_type, fight_id, 0, hostility),
    )


async def _player_details(code: str, fight_id: int) -> list[dict]:
    details = await _report_field(
        code,
        "playerDetails(fightIDs: $fightIDs, includeCombatantInfo: true)",
        ", $fightIDs: [Int]",
        {"fightIDs": [fight_id]},
        "playerDetails",
    )
    groups = ((details or {}).get("data") or {}).get("playerDetails") or {}
    return [p for role in ("tanks", "healers", "dps") for p in groups.get(role) or [] if isinstance(p, dict)]


async def _budget() -> tuple[float | None, float | None]:
    """(remaining points, hourly limit), or (None, None) when unknown."""
    try:
        rl = await wcl_client.acheck_rate_limit()
        limit = float(rl["limitPerHour"])
        return limit - float(rl["pointsSpentThisHour"]), limit
    except Exception:  # noqa: BLE001 - budget unknown ⇒ no shrink, no postponement
        return None, None


async def _ensure_budget(stage: str) -> None:
    """Postpone instead of eating the share of the hourly budget chat lookups need."""
    remaining, limit = await _budget()
    if remaining is not None and limit and remaining < CHAT_RESERVE_SHARE * limit:
        raise WclBudgetLow(f"{remaining:.0f} of {limit:.0f} WCL points left before {stage}")


async def _source_id(code: str, name: str) -> int | None:
    """The player's actor id from the cached report summary (24 h, shared with chat)."""
    summary = await load_report_summary(code)
    wanted = (name or "").casefold()
    for actor_id, player in (summary.players if summary else {}).items():
        if player.name.casefold() == wanted:
            return int(actor_id)
    return None


async def talent_names() -> dict[int, str]:
    """Talent-entry id → name from the optional source (off unless configured; R5 §6)."""
    url = settings.wcl_guide_talent_names_url
    if not url:
        return {}

    async def load() -> TalentNames | None:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        names: dict[int, str] = {}

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for entry in node.get("entries") or []:
                    if isinstance(entry, dict) and entry.get("id") and entry.get("name"):
                        names[int(entry["id"])] = str(entry["name"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(response.json())
        return TalentNames(names=names) if names else None

    try:
        cached = await get_or_load(
            CacheFamily.TALENT_NAMES, keys.talent_names(hashlib.sha1(url.encode()).hexdigest()[:10]), TalentNames, load
        )
    except Exception as exc:  # noqa: BLE001 - names are optional
        logger.warning("talent names unavailable: %s", exc)
        return {}
    return cached.names if cached else {}


# --- the sheet ---------------------------------------------------------------------------


def _metric(briefing: GenerationBriefing) -> str:
    if briefing.content_type == "mplus":
        return "playerscore"
    return "hps" if briefing.role == "healer" else "dps"


async def _collect(briefing: GenerationBriefing) -> DataSheet:
    await _ensure_budget("rankings")
    zones = await load_world_zones()
    zone = (mplus_zone_from if briefing.content_type == "mplus" else raid_zone_from)(zones) or {}
    encounters = [e for e in zone.get("encounters") or [] if e.get("id")][:ENCOUNTERS]
    metric = _metric(briefing)
    if briefing.content_type == "mplus":
        difficulties = [MYTHIC_PLUS_DIFFICULTY_ID]
    else:
        difficulties = [MYTHIC_DIFFICULTY_ID, HEROIC_DIFFICULTY_ID]  # Heroic when Mythic is thin

    entries_by_encounter: list[list[dict]] = []
    difficulty = difficulties[0]
    for difficulty in difficulties:
        results = await gather_settled(*(_rankings(int(e["id"]), briefing, metric, difficulty) for e in encounters))
        entries_by_encounter = [r if isinstance(r, list) else [] for r in results]
        if sum(len(r) for r in entries_by_encounter) >= MIN_RANKINGS:
            break
    all_entries = [e for r in entries_by_encounter for e in r]

    cohort = cohort_from(entries_by_encounter, settings.wcl_guide_datasheet_min_sample)

    async def casts(entry: dict):
        code, fight_id = entry["report"]["code"], int(entry["report"]["fightID"])
        # Source id from the cached report summary; the player's own (cached) Casts table
        # has every ability — the whole-raid table lists only the top few.
        source_id = await _source_id(code, str(entry.get("name") or ""))
        if source_id is None:
            return None, entry
        abilities = await source_casts(code, fight_id, source_id)
        if not abilities:
            return None, entry
        total = sum(a["total"] for a in abilities)
        return CastsEntry(str(entry.get("name")), source_id, None, None, total, abilities), entry

    await _ensure_budget("player casts")

    cast_results = await gather_settled(*(casts(e) for e in cohort))
    members = []
    sources: list[tuple[dict, int]] = []  # (ranking entry, source id) for deeper reads
    for res in cast_results:
        if isinstance(res, BaseException) or res[0] is None:
            continue
        cast_entry, entry = res
        minutes = float(entry.get("duration") or 0) / 60000
        if minutes > 0:
            members.append((cast_entry, minutes))
            if cast_entry.source_id is not None:
                sources.append((entry, int(cast_entry.source_id)))

    await _ensure_budget("cast events, uptimes and stats")
    gap_results = await gather_settled(
        *(_events(e["report"]["code"], int(e["report"]["fightID"]), sid) for e, sid in sources[:GAP_PLAYERS])
    )
    gaps = merge_gaps([shortest_gaps(r) for r in gap_results if isinstance(r, list)])

    detail_set = sources[:DETAIL_PLAYERS]
    aura_results = await gather_settled(
        *(
            _aura_table(e["report"]["code"], int(e["report"]["fightID"]), sid, kind)
            for e, sid in detail_set
            for kind in ("buff", "debuff")
        )
    )
    kinds = [kind for _ in detail_set for kind in ("buff", "debuff")]
    aura_tables = [(k, t) for k, t in zip(kinds, aura_results) if isinstance(t, dict)]
    detail_results = await gather_settled(
        *(_player_details(e["report"]["code"], int(e["report"]["fightID"])) for e, _ in detail_set)
    )
    details = []
    for (entry, _), res in zip(detail_set, detail_results):
        if isinstance(res, list):
            name = str(entry.get("name") or "").casefold()
            details += [p for p in res if str(p.get("name") or "").casefold() == name]

    builds, picks = talent_summary(all_entries, await talent_names())
    brackets = [float(e["bracketData"]) for e in all_entries if isinstance(e.get("bracketData"), (int, float))]
    sample = len(members)
    return DataSheet(
        class_name=briefing.class_name,
        spec=briefing.spec,
        content_type=briefing.content_type,
        scope=SampleScope(
            zone_id=zone.get("id"),
            zone_name=zone.get("name"),
            difficulty=difficulty,
            key_level_floor=int(min(brackets)) if briefing.content_type == "mplus" and brackets else None,
            encounters=[str(e.get("name")) for e in encounters],
            metric=metric,
            sample_size=sample,
            collected_at=datetime.now(UTC),
        ),
        sufficient=sample >= settings.wcl_guide_datasheet_min_sample and len(all_entries) >= MIN_RANKINGS,
        abilities=ability_stats(members, gaps),
        uptimes=uptime_stats(aura_tables, len(detail_set)),
        talent_builds=builds,
        talent_pick_rates=picks,
        stat_spread=stat_spread(details),
        item_level_median=(
            (median_range(brackets) or {}).get("median") if briefing.content_type == "raid" else None
        ),
    )


async def build_data_sheet(briefing: GenerationBriefing) -> DataSheet:
    """The cached data sheet for the briefing's spec, content type and patch/season."""
    scope = briefing.mplus_season if briefing.content_type == "mplus" else briefing.live_patch
    key = keys.spec_datasheet(briefing.content_type, briefing.class_name, briefing.spec, scope or "unknown")

    async def load() -> DataSheetCache:
        with background_lane():
            sheet = await _collect(briefing)
        return DataSheetCache(data=sheet.model_dump(mode="json"))

    cached = await get_or_load(CacheFamily.SPEC_DATASHEET, key, DataSheetCache, load)
    return DataSheet.model_validate(cached.data)


def format_data_sheet_table(sheet: DataSheet) -> str:
    """A readable dump for ``python -m backend.evals.guides datasheet`` (quickstart §3)."""
    s = sheet.scope
    lines = [
        f"{sheet.spec} {sheet.class_name} — {sheet.content_type} — {s.zone_name} (difficulty {s.difficulty})",
        f"metric {s.metric}, sample {s.sample_size} players, sufficient={sheet.sufficient}, "
        f"encounters: {', '.join(s.encounters)}",
        "",
        f"{'ability':32} {'id':>8} {'cpm p50':>8} {'p25':>6} {'p75':>6} {'min gap':>8} {'users':>5}",
    ]
    for a in sheet.abilities:
        gap = f"{a.min_gap_s:g}s" if a.min_gap_s else "-"
        lines.append(
            f"{a.name[:32]:32} {a.ability_id:>8} {a.casts_per_min_median or 0:>8.2f} "
            f"{a.casts_per_min_p25 or 0:>6.2f} {a.casts_per_min_p75 or 0:>6.2f} {gap:>8} {a.players_using:>5}"
        )
    lines += ["", "uptimes:"]
    lines += [f"  {u.kind:6} {u.name[:30]:30} {u.uptime_pct_median:6.1f}%  ({u.players} players)" for u in sheet.uptimes]
    lines += ["", "top builds:"]
    lines += [f"  {b.talent_ids_hash} {b.share_pct:5.1f}% ({b.players})" for b in sheet.talent_builds]
    lines += ["", "stats:"]
    lines += [f"  {st.stat:12} median {st.median_rating:g} (p25 {st.p25:g}, p75 {st.p75:g})" for st in sheet.stat_spread]
    if sheet.item_level_median is not None:
        lines.append(f"\nitem level median {sheet.item_level_median:g}")
    return "\n".join(lines)
