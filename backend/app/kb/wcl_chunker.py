"""Stored Warcraft Logs responses rendered as knowledge base chunks (feature 043, sc-112).

Raw JSON embeds badly, so each recognised response becomes short readable text with the key
names spelled out, plus filter columns taken from the query variables and the response (never
from a model). Recognised (anything else yields no chunks, research R8):

* report summaries (``REPORT_SUMMARY`` / its batch form): one ``fight:<code>:<id>`` chunk per
  boss fight, with the roster;
* ``table`` bodies: one ``table`` chunk for the fight and metric with the top entries, and, for
  a table of more than :data:`TOP_N` players, one ``player:<key>`` chunk per player. A table
  filtered to one source lists that player's top abilities instead.

A table body doesn't say which boss or difficulty it covers; the same report's fight-summary
chunk does, so the indexer looks those up (:class:`FightContext`) and passes them in.

Report codes come from what the writer resolved exactly (``exact_report_codes``) and, for a
batch summary, only a report object whose ``code`` is one of them is used (like 039's grants).
Labels such as the table metric come from the query text on the live path; stored rows keep
no query text, so the backfill infers the metric from the body or skips the table.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .chunks import MAX_TEXT, ChunkDraft, PlayerRef, bounded, humanise
from .names import class_spec, difficulty_name, name_key, player

TOP_N = 10  # entries in a table chunk
MAX_PLAYERS = 40  # per-player chunks per table, and players listed per chunk
MAX_FIGHTS = 60  # fight-summary chunks per report
MAX_DEATHS = 20
SUMMARY_TOP = 5  # per list in a Summary-table chunk

_DATA_TYPE_RE = re.compile(r"\btable\s*\(\s*[^)]*?\bdataType\s*:\s*(\w+)")
_HOSTILITY_RE = re.compile(r"\btable\s*\(\s*[^)]*?\bhostilityType\s*:\s*(\w+)")
METRIC_LABELS = {
    "Summary": "Fight overview",
    "DamageDone": "Damage done",
    "DamageTaken": "Damage taken",
    "Healing": "Healing",
    "Casts": "Casts",
    "Deaths": "Deaths",
    "Buffs": "Buff uptime",
    "Debuffs": "Debuff uptime",
    "Auras": "Aura uptime",  # inferred from a stored body: buffs or debuffs, unknown which
    "Dispels": "Dispels",
    "Interrupts": "Interrupts",
    "Resources": "Resources",
    "Threat": "Threat",
    "Survivability": "Survivability",
    "Summons": "Summons",
}


@dataclass(frozen=True)
class FetchSource:
    """One stored fetch as the chunker reads it."""

    raw_fetch_id: str
    report_codes: tuple[str, ...]
    variables: dict[str, Any]
    body: dict[str, Any]
    metric: str | None = None  # the table's dataType from the query text; None = unknown
    hostility: str | None = None


@dataclass(frozen=True)
class FightContext:
    """What a report's fight-summary chunk says about one fight."""

    name: str | None = None
    encounter_id: int | None = None
    difficulty: int | None = None
    kill: bool | None = None
    start_time: datetime | None = None
    zone_id: int | None = None
    guild: str | None = None
    players: tuple[PlayerRef, ...] = field(default_factory=tuple)

    def phrase(self) -> str:
        """ "Heroic Ula'tek, kill" (as much as is known)."""
        title = " ".join(p for p in (difficulty_name(self.difficulty), self.name) if p)
        outcome = None if self.kill is None else ("kill" if self.kill else "wipe")
        return ", ".join(p for p in (title, outcome) if p)


def source_from_query(
    raw_fetch_id: str, query: str, variables: dict, codes: Iterable[str], body: dict
) -> FetchSource:
    """The live path: the writer's response, with the metric and hostility from its query."""
    metric = _DATA_TYPE_RE.search(query)
    hostility = _HOSTILITY_RE.search(query)
    return FetchSource(
        raw_fetch_id, tuple(codes), dict(variables), body,
        metric.group(1) if metric else None, hostility.group(1) if hostility else None,
    )


def _report_objects(source: FetchSource) -> list[tuple[str, dict]]:
    """(code, report object) pairs a summary body holds, codes checked against the source's."""
    report_data = ((source.body.get("data") or {}).get("reportData")) or {}
    if not isinstance(report_data, dict):
        return []
    out = []
    for value in report_data.values():
        if not isinstance(value, dict):
            continue
        code = value.get("code")
        if code in source.report_codes:
            out.append((code, value))
        elif code is None and len(source.report_codes) == 1 and len(report_data) == 1:
            out.append((source.report_codes[0], value))
    return out


def _table(source: FetchSource) -> dict | None:
    report = (((source.body.get("data") or {}).get("reportData")) or {}).get("report")
    table = report.get("table") if isinstance(report, dict) else None
    data = table.get("data") if isinstance(table, dict) else None
    return data if isinstance(data, dict) else None


def infer_metric(table: dict) -> str | None:
    """The metric a stored table body shows when the query isn't known (the backfill)."""
    if "playerDetails" in table and "composition" in table:
        return "Summary"
    if isinstance(table.get("auras"), list):
        return "Auras"
    entries = table.get("entries")
    if isinstance(entries, list) and entries and all(isinstance(e, dict) and "deathTime" in e for e in entries[:5]):
        return "Deaths"
    return None  # plain entries: damage, healing or casts, which the body doesn't say


def needed_fights(source: FetchSource) -> tuple[str | None, list[int]]:
    """(report code, fight ids) whose :class:`FightContext` a table chunk would use."""
    if _table(source) is None or len(source.report_codes) != 1:
        return None, []
    fight = _single_fight(source.variables)
    return source.report_codes[0], [fight] if fight is not None else []


def chunk_fetch(source: FetchSource, contexts: Mapping[int, FightContext] | None = None) -> list[ChunkDraft]:
    """The chunks of one stored fetch; ``[]`` for shapes this module doesn't know."""
    if not source.report_codes:
        return []  # 039 never serves a row that names no report
    table = _table(source)
    if table is not None:
        if len(source.report_codes) != 1:
            return []
        metric = source.metric or infer_metric(table)
        if metric is None:
            return []
        fight = _single_fight(source.variables)
        context = (contexts or {}).get(fight) if fight is not None else None
        return _table_chunks(source, table, metric, fight, context or FightContext())
    drafts: list[ChunkDraft] = []
    for code, report in _report_objects(source):
        if isinstance(report.get("fights"), list):
            drafts += _summary_chunks(code, report)
    return drafts


# --- report summaries ---------------------------------------------------------------------


def _ms_time(base_ms: Any, offset_ms: Any = 0) -> datetime | None:
    if not isinstance(base_ms, int):
        return None
    offset = offset_ms if isinstance(offset_ms, int) else 0
    return datetime.fromtimestamp((base_ms + offset) / 1000, UTC)


def _summary_chunks(code: str, report: dict) -> list[ChunkDraft]:
    actors = ((report.get("masterData") or {}).get("actors")) or []
    by_id = {a["id"]: a for a in actors if isinstance(a, dict) and isinstance(a.get("id"), int) and a.get("name")}
    zone = report.get("zone") or {}
    guild = (report.get("guild") or {}).get("name")
    head = ", ".join(p for p in (report.get("title"), zone.get("name"), f"guild {guild}" if guild else None) if p)
    drafts = []
    fights = [f for f in report["fights"] if isinstance(f, dict) and f.get("encounterID") and isinstance(f.get("id"), int)]
    for fight in fights[:MAX_FIGHTS]:
        roster = [
            player(by_id[i]["name"], by_id[i].get("subType"), None, i)
            for i in (fight.get("friendlyPlayers") or [])
            if i in by_id
        ][:MAX_PLAYERS]
        context = FightContext(
            name=fight.get("name"),
            encounter_id=fight.get("encounterID"),
            difficulty=fight.get("difficulty") if isinstance(fight.get("difficulty"), int) else None,
            kill=fight.get("kill") if isinstance(fight.get("kill"), bool) else None,
        )
        facts = [context.phrase()]
        if fight.get("keystoneLevel"):
            facts.append(f"keystone +{fight['keystoneLevel']}")
        if isinstance(fight.get("keystoneTime"), int):
            facts.append(f"{round(fight['keystoneTime'] / 1000)} s")
        if fight.get("averageItemLevel"):
            facts.append(f"item level {round(fight['averageItemLevel'])}")
        if fight.get("size"):
            facts.append(f"{fight['size']} players")
        text = f"Report {code}" + (f" ({head})" if head else "") + f", fight {fight['id']}: "
        text += ", ".join(f for f in facts if f) + "."
        if roster:
            text += " Roster: " + ", ".join(_who(p) for p in roster) + "."
        drafts.append(
            ChunkDraft(
                chunk_key=f"fight:{code}:{fight['id']}",
                label=f"fight {fight['id']} summary",
                text=bounded(text, MAX_TEXT),
                report_code=code,
                zone_id=zone.get("id") if isinstance(zone.get("id"), int) else None,
                encounter_id=context.encounter_id,
                difficulty=context.difficulty,
                fight_id=fight["id"],
                kill=context.kill,
                start_time=_ms_time(report.get("startTime"), fight.get("startTime")),
                players=tuple(roster),
                guild=guild,
                extra={"fight_name": fight.get("name")} if fight.get("name") else {},
            )
        )
    return drafts


# --- tables ---------------------------------------------------------------------------------


def _single_fight(variables: dict) -> int | None:
    ids = variables.get("fightIDs")
    if isinstance(ids, list) and len(ids) == 1 and isinstance(ids[0], int):
        return ids[0]
    return None


def _who(p: PlayerRef) -> str:
    kind = " ".join(x for x in (p.spec, p.class_name) if x)
    return f"{p.name} ({kind})" if kind else p.name


def _entry_player(entry: dict) -> PlayerRef | None:
    """A player from a table entry (``type`` = class, ``icon`` = "Class-Spec"); None for NPCs."""
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    icon = entry.get("icon") if isinstance(entry.get("icon"), str) else ""
    cls, spec, _ = class_spec(entry.get("type"), icon.partition("-")[2] or None)
    if cls is None:
        return None
    return PlayerRef(name, name_key(name), cls, spec, entry.get("id") if isinstance(entry.get("id"), int) else None)


def _amount(entry: dict) -> float | None:
    total = entry.get("total")
    return total if isinstance(total, (int, float)) else None


def _table_chunks(
    source: FetchSource, table: dict, metric: str, fight: int | None, context: FightContext
) -> list[ChunkDraft]:
    code = source.report_codes[0]
    label = METRIC_LABELS.get(metric, metric)
    if source.hostility == "Enemies":
        label += " (enemies)"
    where = f"fight {fight}" if fight is not None else "all fights"
    head = f"Report {code}, {where}"
    if context.phrase():
        head += f" ({context.phrase()})"
    if isinstance(table.get("totalTime"), int) and table["totalTime"] > 0:
        head += f", {round(table['totalTime'] / 1000)} s"
    extra: dict[str, Any] = {"metric": metric}
    if source.hostility:
        extra["hostility"] = source.hostility
    if context.name:
        extra["fight_name"] = context.name
    base = dict(
        report_code=code, zone_id=context.zone_id, encounter_id=context.encounter_id,
        difficulty=context.difficulty, fight_id=fight, kill=context.kill,
        start_time=context.start_time, guild=context.guild,
    )
    source_id = source.variables.get("sourceID")
    if isinstance(source_id, int) and source_id:
        return _source_chunk(source_id, table, head, label, where, context, base, extra)
    if metric == "Summary":
        body, players = _summary_table_text(table)
    elif metric == "Deaths":
        body, players = _deaths_text(table)
    elif metric in ("Buffs", "Debuffs", "Auras"):
        body, players = _auras_text(table), []
    else:
        return _entry_chunks(table, head, label, where, base, extra)
    if not body:
        return []
    return [
        ChunkDraft(
            chunk_key="table", label=f"{where} {label}", text=bounded(f"{head}. {label}: {body}", MAX_TEXT),
            players=tuple(players[:MAX_PLAYERS]), extra=extra, **base,
        )
    ]


def _entry_chunks(table: dict, head: str, label: str, where: str, base: dict, extra: dict) -> list[ChunkDraft]:
    entries = [e for e in (table.get("entries") or []) if isinstance(e, dict) and _amount(e) is not None]
    if not entries:
        return []
    entries.sort(key=lambda e: _amount(e) or 0, reverse=True)
    rows = [(e, _entry_player(e)) for e in entries]
    shown = "; ".join(
        f"{_who(p) if p else e.get('name', '?')} {humanise(_amount(e) or 0)}" for e, p in rows[:TOP_N]
    )
    of = f" (top {TOP_N} of {len(rows)})" if len(rows) > TOP_N else ""
    players = tuple(p for _, p in rows if p)[:MAX_PLAYERS]
    drafts = [
        ChunkDraft(
            chunk_key="table", label=f"{where} {label}", text=bounded(f"{head}. {label}{of}: {shown}.", MAX_TEXT),
            players=players, extra=extra, **base,
        )
    ]
    if len(rows) <= TOP_N:
        return drafts
    total = sum(_amount(e) or 0 for e, _ in rows)
    for rank, (entry, who) in enumerate(rows, start=1):
        if who is None:
            continue
        if len(drafts) > MAX_PLAYERS:
            break
        share = f", {100 * (_amount(entry) or 0) / total:.1f}% of the total" if total else ""
        text = f"{head}. {label}: {_who(who)} {humanise(_amount(entry) or 0)}, rank {rank} of {len(rows)}{share}."
        drafts.append(
            ChunkDraft(
                chunk_key=f"player:{who.key}", label=f"{who.name}, {where} {label}", text=bounded(text, MAX_TEXT),
                players=(who,), class_name=who.class_name, spec=who.spec,
                role=class_spec(who.class_name, who.spec)[2], extra=extra, **base,
            )
        )
    return drafts


def _source_chunk(
    source_id: int, table: dict, head: str, label: str, where: str, context: FightContext, base: dict, extra: dict
) -> list[ChunkDraft]:
    """A table filtered to one actor: its entries are that actor's abilities."""
    entries = [e for e in (table.get("entries") or []) if isinstance(e, dict) and _amount(e) is not None]
    if not entries:
        return []
    entries.sort(key=lambda e: _amount(e) or 0, reverse=True)
    who = next((p for p in context.players if p.id == source_id), None)
    name = _who(who) if who else f"actor #{source_id}"
    shown = "; ".join(f"{e.get('name', '?')} {humanise(_amount(e) or 0)}" for e in entries[:TOP_N])
    extra = {**extra, "source_id": source_id}
    return [
        ChunkDraft(
            chunk_key=f"source:{source_id}",
            label=f"{who.name if who else f'actor #{source_id}'}, {where} {label}",
            text=bounded(f"{head}. {label} by ability, {name}: {shown}.", MAX_TEXT),
            players=(who,) if who else (), class_name=who.class_name if who else None,
            spec=who.spec if who else None, extra=extra, **base,
        )
    ]


def _summary_table_text(table: dict) -> tuple[str, list[PlayerRef]]:
    details = table.get("playerDetails") or {}
    players: list[PlayerRef] = []
    counts = []
    for group in ("tanks", "healers", "dps"):
        members = [m for m in (details.get(group) or []) if isinstance(m, dict) and m.get("name")]
        counts.append(f"{len(members)} {group}")
        for m in members:
            specs = m.get("specs") or []
            spec = specs[0].get("spec") if specs and isinstance(specs[0], dict) else None
            players.append(player(m["name"], m.get("type"), spec, m.get("id") if isinstance(m.get("id"), int) else None))
    parts = ["composition " + ", ".join(counts)]
    for key, title in (("damageDone", "damage done"), ("healingDone", "healing")):
        rows = sorted(
            (e for e in (table.get(key) or []) if isinstance(e, dict) and _amount(e) is not None),
            key=lambda e: _amount(e) or 0, reverse=True,
        )[:SUMMARY_TOP]
        if rows:
            parts.append(f"top {title}: " + "; ".join(f"{e.get('name', '?')} {humanise(_amount(e) or 0)}" for e in rows))
    deaths = [d.get("name") for d in (table.get("deathEvents") or []) if isinstance(d, dict) and d.get("name")]
    if deaths:
        parts.append(f"{len(deaths)} deaths: " + ", ".join(deaths[:MAX_DEATHS]))
    return ". ".join(parts) + ".", players


def _clock(ms: Any) -> str:
    seconds = int(ms // 1000) if isinstance(ms, (int, float)) else 0
    return f"{seconds // 60}:{seconds % 60:02d}"


def _deaths_text(table: dict) -> tuple[str, list[PlayerRef]]:
    entries = [e for e in (table.get("entries") or []) if isinstance(e, dict) and e.get("name")]
    entries.sort(key=lambda e: e.get("deathTime") or 0)
    shown = []
    players: list[PlayerRef] = []
    for e in entries[:MAX_DEATHS]:
        who = _entry_player(e)
        if who:
            players.append(who)
        ability = e.get("ability") or e.get("killingBlow") or {}
        to = f" to {ability['name']}" if isinstance(ability, dict) and ability.get("name") else ""
        shown.append(f"{_who(who) if who else e['name']} at {_clock(e.get('deathTime'))}{to}")
    return "; ".join(shown) + ("." if shown else ""), players


def _auras_text(table: dict) -> str:
    total = table.get("totalTime") if isinstance(table.get("totalTime"), int) else 0
    auras = [a for a in (table.get("auras") or []) if isinstance(a, dict) and a.get("name")]
    auras.sort(key=lambda a: a.get("totalUptime") or 0, reverse=True)
    shown = []
    for a in auras[:TOP_N]:
        uptime = a.get("totalUptime")
        share = f" {100 * uptime / total:.0f}%" if total and isinstance(uptime, (int, float)) else ""
        shown.append(f"{a['name']}{share}")
    return "; ".join(shown) + ("." if shown else "")
