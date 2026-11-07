"""What the app already stored about a tracked raid (feature 072, backend half of sc-142).

``summarize`` answers ``GET /api/raids/{report_code}/summary`` (board ``contract:raid-summary``):
participants, duration and the caller's own characters' parses, read from the raw WCL store.
Rules:

* Only a raid tracked in the caller's workspace is answered (None → the route's 404).
* Stored rows are read only through the 039 visibility rule (``read_visible_summary`` and
  ``read_visible_parts``, both ``fetch_visible_clause``), with the store's own re-verify window.
* The rows read are the newest own report summary naming the code and the exact rows our own tools
  would have stored for it (``part_keys``): playerDetails for the whole report, the kickoff's
  per-boss Summary tables and the default rankings (Rankings, Historical) for the whole report and
  per boss. A malformed part of a stored body is dropped, never an error.
* "My characters" are the workspace's own profile characters, matched to stored players by name
  and, where the stored data has them, realm and region; never from request input.
* Uploader-controlled text is neutralised, stripped of control characters and capped.
* Re-verify (board ``decision:072-reverify``): when a summary of the raid is stored but none is
  visible, ONE report-summary query (our tools' own) is sent through the WCL client as the
  caller's workspace, at most once per workspace and raid per :data:`REVERIFY_COOLDOWN_S`, within
  :data:`REVERIFY_TIMEOUT_S`. When WCL returned that report, its status and the workspace's grant
  are written in this transaction (the fetch sink writes them too, but later), and the rows are
  read again under the unchanged rule. Participants, tables and rankings are never fetched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import unicodedata
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.cache.normalize import server_slug
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import _flight_key
from wcl_agent.game.constants import DIFFICULTY_NAMES, normalize_class_name
from wcl_agent.game.roster import roster_snapshot
from wcl_agent.tools.participants import _FIELDS as PARTICIPANT_FIELDS
from wcl_agent.tools.participants import participants_from_player_details
from wcl_agent.tools.report_tools import (
    MAX_NAME_CHARS,
    _bounded,
    _fight_ids,
    _summary_from,
    _table_query,
    neutralise,
    report_query,
)

from ..config import settings
from ..db import repository as repo
from ..db.models import UserCharacter
from ..repositories.raw_fetches import (
    ReportStatus,
    grant_codes,
    read_visible_parts,
    read_visible_summary,
    record_report_status,
    stored_summary_exists,
)
from ..tenancy.context import RequestIdentity, current_identity
from .kickoff_prefetch import pick_boss_fights

logger = logging.getLogger(__name__)

MAX_PARTICIPANTS = 100
MAX_PARSES = 50
REVERIFY_TIMEOUT_S = 5.0
REVERIFY_COOLDOWN_S = 600.0
# (workspace, report) -> when its last re-verify started (monotonic); entries older than the
# cooldown are dropped on the next attempt, so this holds at most one cooldown window's raids.
_reverified: dict[tuple[uuid.UUID, str], float] = {}
_OFF_LOOP_BYTES = 256_000  # bigger stored JSON is decoded in a thread
_FIGHTS_DECL = ", $fightIDs: [Int]"
# The rankings field get_report_rankings sends with its defaults (compare Rankings, timeframe
# Historical); a test pins the key against the tool.
_RANKINGS_FIELD = "rankings(fightIDs: $fightIDs, compare: Rankings, timeframe: Historical)"
_REPORT = ("data", "reportData", "report")
# The parts read from each stored row, by index (read_visible_parts' ``paths``).
_PATHS = (
    (*_REPORT, "playerDetails"),  # 0: participants / player-details tools, {"data": {"playerDetails"}}
    (*_REPORT, "region"),  # 1: the participants tool's report region {"slug"}
    (*_REPORT, "table", "data", "playerDetails"),  # 2: a Summary table's {"tanks", "healers", "dps"}
    (*_REPORT, "rankings"),  # 3: report rankings {"data": [fight, ...]}
)

Role = Literal["tank", "healer", "dps"]
PartKind = Literal["details", "table", "rankings"]


class Participant(BaseModel):
    name: str
    class_name: str | None = None
    spec: str | None = None
    role: Role | None = None


class Parse(BaseModel):
    encounter: str | None = None
    difficulty: str | None = None
    percentile: float | None = None


class MyCharacter(BaseModel):
    name: str
    class_name: str | None = None
    spec: str | None = None
    parses: list[Parse] = []


class RaidSummary(BaseModel):
    report_code: str
    has_data: bool
    duration_ms: int | None = None
    participants: list[Participant] = []
    my_characters: list[MyCharacter] = []
    fetched_at: datetime | None = None


def _text(value: Any) -> str | None:
    """Uploader-controlled text as plain data: neutralised, no control characters, capped."""
    if not isinstance(value, str):
        return None
    cleaned = "".join(c for c in neutralise(value[: MAX_NAME_CHARS * 4]) if unicodedata.category(c) != "Cc")
    return _bounded(cleaned.strip()) or None


def _key(query: str, variables: dict[str, Any]) -> str:
    return _flight_key(query, variables)


def part_keys(code: str, boss_fights: list[int]) -> dict[str, PartKind]:
    """The store keys of the rows our tools would have written for ``code``, in reading order:
    the whole-report rows first, then per boss fight. Each key is the tool's own query and
    variables (``_flight_key``)."""
    whole = {"code": code, "fightIDs": _fight_ids(0)}
    keys: dict[str, PartKind] = {
        _key(report_query(PARTICIPANT_FIELDS, _FIGHTS_DECL), whole): "details",
        _key(report_query("playerDetails(fightIDs: $fightIDs)", _FIGHTS_DECL), whole): "details",
        _key(report_query(_RANKINGS_FIELD, _FIGHTS_DECL), whole): "rankings",
    }
    for fight in boss_fights:
        field, decls, variables = _table_query("Summary", "Friendlies", fight, 0, 0)
        keys[_key(report_query(field, decls), {"code": code, **variables})] = "table"
        keys[_key(report_query(_RANKINGS_FIELD, _FIGHTS_DECL), {"code": code, "fightIDs": _fight_ids(fight)})] = (
            "rankings"
        )
    return keys


async def _loads(raw: bytes | None) -> Any:
    """Stored JSON decoded (in a thread when big); None when absent or not JSON."""
    if raw is None:
        return None
    try:
        if len(raw) > _OFF_LOOP_BYTES:
            return await asyncio.to_thread(json.loads, raw)
        return json.loads(raw)
    except ValueError:
        return None


def _report_object(body: Any, code: str) -> dict[str, Any] | None:
    """The report object for ``code`` in a single or batch summary body, picked by the ``code``
    WCL returned in it."""
    data = body.get("data") if isinstance(body, dict) else None
    reports = data.get("reportData") if isinstance(data, dict) else None
    if not isinstance(reports, dict):
        return None
    return next((r for r in reports.values() if isinstance(r, dict) and r.get("code") == code), None)


def _duration(report: dict[str, Any]) -> int | None:
    start, end = report.get("startTime"), report.get("endTime")
    if not all(isinstance(t, int) and not isinstance(t, bool) for t in (start, end)) or end < start:
        return None
    return end - start


def _fight_names(report: dict[str, Any]) -> tuple[dict[int, str], list[int]]:
    """(fight id → name, the kickoff's boss fights) of a stored summary; empty when malformed."""
    try:
        summary = _summary_from(str(report.get("code")), report)
        return {f.id: f.name for f in summary.fights}, pick_boss_fights(summary)
    except (KeyError, TypeError, ValueError, AttributeError):
        return {}, []


def _detail_rows(details: Any, region: Any) -> list[dict[str, Any]]:
    """``participants_from_player_details`` rows with string names; [] for a malformed part."""
    region = region.get("slug") if isinstance(region, dict) else None
    try:
        rows = participants_from_player_details(details, region if isinstance(region, str) else None)
    except (KeyError, TypeError, ValueError, AttributeError):
        return []
    return [r for r in rows if isinstance(r.get("name"), str)]


def _actor_rows(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The summary's players (name and class; no realm, spec or role)."""
    actors = (report or {}).get("masterData")
    actors = actors.get("actors") if isinstance(actors, dict) else None
    rows = []
    for actor in actors if isinstance(actors, list) else []:
        if isinstance(actor, dict) and isinstance(actor.get("name"), str):
            sub = actor.get("subType")
            klass = normalize_class_name(sub) if isinstance(sub, str) else None
            rows.append({"name": actor["name"], "realm": None, "region": None,
                         "class": roster_snapshot().class_display(klass) if klass else None,
                         "spec": None, "role": None})
    return rows


def _participant(row: dict[str, Any]) -> Participant | None:
    name = _text(row.get("name"))
    if name is None:
        return None
    role = row.get("role")
    return Participant(
        name=name, class_name=_text(row.get("class")), spec=_text(row.get("spec")),
        role=role if role in ("tank", "healer", "dps") else None,
    )


def _ranked(rankings: Any) -> Iterator[tuple[int | None, dict[str, Any], dict[str, Any]]]:
    """(fight id, fight, character) for every ranked character of a stored rankings part."""
    fights = rankings.get("data") if isinstance(rankings, dict) else None
    for fight in fights if isinstance(fights, list) else []:
        if not isinstance(fight, dict):
            continue
        fight_id = fight.get("fightID") if isinstance(fight.get("fightID"), int) else None
        roles = fight.get("roles") if isinstance(fight.get("roles"), dict) else {}
        for group in ("tanks", "healers", "dps"):
            members = roles.get(group)
            characters = members.get("characters") if isinstance(members, dict) else None
            for char in characters if isinstance(characters, list) else []:
                if isinstance(char, dict):
                    yield fight_id, fight, char


def _is_mine(char: UserCharacter, name: Any, realm: Any, region: Any) -> bool:
    """A stored player is this profile character: same name, and same realm and region wherever
    the stored data names them."""
    if not isinstance(name, str) or name.casefold() != char.name.casefold():
        return False
    if isinstance(realm, str) and realm and server_slug(realm) != server_slug(char.server):
        return False
    return not (isinstance(region, str) and region and region.casefold() != char.region.casefold())


def _parse(fight: dict[str, Any], ranked: dict[str, Any], names: dict[int, str]) -> Parse:
    encounter = fight.get("encounter")
    name = encounter.get("name") if isinstance(encounter, dict) else None
    if name is None and isinstance(fight.get("fightID"), int):
        name = names.get(fight["fightID"])
    difficulty = fight.get("difficulty")
    percent = ranked.get("rankPercent")
    valid = isinstance(percent, (int, float)) and not isinstance(percent, bool) and 0 <= percent <= 100
    return Parse(
        encounter=_text(name),
        difficulty=DIFFICULTY_NAMES.get(difficulty) if isinstance(difficulty, int) else None,
        percentile=float(percent) if valid else None,
    )


def _my_characters(
    own: list[UserCharacter], rows: list[dict[str, Any]], rankings: list[Any], names: dict[int, str]
) -> list[MyCharacter]:
    mine = []
    for char in own:
        row = next((r for r in rows if _is_mine(char, r["name"], r.get("realm"), r.get("region"))), None)
        parses: list[Parse] = []
        fights: set[int] = set()  # a fight seen in the whole-report and the per-boss rankings counts once
        spec = row.get("spec") if row else None
        for part in rankings:
            for fight_id, fight, ranked in _ranked(part):
                server = ranked.get("server") if isinstance(ranked.get("server"), dict) else {}
                if fight_id in fights or not _is_mine(char, ranked.get("name"), server.get("name"), server.get("region")):
                    continue
                if fight_id is not None:
                    fights.add(fight_id)
                parses.append(_parse(fight, ranked, names))
                spec = spec or ranked.get("spec")
        if row is None and not parses:
            continue
        mine.append(MyCharacter(
            name=_text(char.name) or "?",
            class_name=_text(row.get("class") if row else None) or _text(char.class_name),
            spec=_text(spec),
            parses=parses[:MAX_PARSES],
        ))
    return mine


def _may_reverify(tenant_id: uuid.UUID, code: str) -> bool:
    """At most one re-verify per workspace and raid per cooldown (in-process); claims the slot."""
    now = time.monotonic()
    for key, started in list(_reverified.items()):
        if now - started >= REVERIFY_COOLDOWN_S:
            del _reverified[key]
    if (tenant_id, code) in _reverified:
        return False
    _reverified[(tenant_id, code)] = now
    return True


async def _reverify(session: AsyncSession, identity: RequestIdentity, code: str, now: datetime) -> bool:
    """Ask WCL for the report summary once, as ``identity``'s workspace; when WCL returned that
    report, record its status and grant it to the workspace in this transaction. True when it
    did; any failure (timeout, error, gone, another code) is False."""
    token = current_identity.set(identity)  # the client's store probe and fetch sink act for it
    try:
        async with asyncio.timeout(REVERIFY_TIMEOUT_S):
            data = await wcl_client.get_async_client().query(REPORT_SUMMARY, {"code": code})
    except Exception as exc:  # noqa: BLE001 - any failure leaves the raid unverified
        logger.info("raid summary re-verify failed: %s", type(exc).__name__)
        return False
    finally:
        current_identity.reset(token)
    report = _report_object(data, code)
    if report is None:
        return False
    visibility, end = report.get("visibility"), report.get("endTime")
    status = ReportStatus(
        code, visibility if isinstance(visibility, str) else None,
        end if isinstance(end, int) and not isinstance(end, bool) else None, now,
    )
    await record_report_status(session, [status])
    await grant_codes(session, identity.tenant_id, [code], now)
    return True


async def summarize(
    session: AsyncSession, code: str, *, identity: RequestIdentity, now: datetime
) -> RaidSummary | None:
    """The stored summary of a raid tracked in the caller's workspace; None when it isn't one.
    Raw-store reads only under the visibility rule; one re-verify request at most."""
    tenant_id = identity.tenant_id
    if await repo.get_tracked_raid(session, code, tenant_id=tenant_id) is None:
        return None
    since = now - timedelta(days=settings.raw_store_reverify_days)
    found = await read_visible_summary(session, code, tenant_id=tenant_id, since=since)
    if (
        found is None
        and await stored_summary_exists(session, code)
        and _may_reverify(tenant_id, code)
        and await _reverify(session, identity, code, now)
    ):
        found = await read_visible_summary(session, code, tenant_id=tenant_id, since=since)
    report = _report_object(await _loads(found[0]), code) if found else None
    names, bosses = _fight_names(report) if report else ({}, [])
    keys = part_keys(code, bosses)
    parts = await read_visible_parts(session, list(keys), _PATHS, tenant_id=tenant_id, since=since)

    stamps = [found[1]] if report is not None else []
    detail_rows: list[dict[str, Any]] = []
    rankings: list[Any] = []
    for key, kind in keys.items():  # reading order: whole report first, then per boss
        if key not in parts:
            continue
        fetched_at, raw = parts[key]
        if kind == "rankings":
            value = await _loads(raw[3])
            rankings.append(value)
            used = value is not None
        else:
            if kind == "details":
                rows = _detail_rows(await _loads(raw[0]), await _loads(raw[1]))
            else:
                rows = _detail_rows({"data": {"playerDetails": await _loads(raw[2])}}, None)
            detail_rows += rows
            used = bool(rows)
        if used:
            stamps.append(fetched_at)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for row in detail_rows:  # one row per player: the first source that knew them wins
        realm = row.get("realm") if isinstance(row.get("realm"), str) else None
        ident = (row["name"].casefold(), server_slug(realm) if realm else None)
        if ident not in seen:
            seen.add(ident)
            rows.append(row)
    known = {name for name, _ in seen}
    for actor in _actor_rows(report):  # the summary's players no detail row named
        if actor["name"].casefold() not in known:
            known.add(actor["name"].casefold())
            rows.append(actor)

    participants = [p for p in map(_participant, rows) if p is not None][:MAX_PARTICIPANTS]
    own = await repo.list_own_characters(session, tenant_id=tenant_id)
    mine = _my_characters(own, rows, rankings, names)
    has_data = report is not None or bool(participants) or bool(mine)
    return RaidSummary(
        report_code=code,
        has_data=has_data,
        duration_ms=_duration(report) if report else None,
        participants=participants,
        my_characters=mine,
        fetched_at=max(stamps) if has_data and stamps else None,
    )
