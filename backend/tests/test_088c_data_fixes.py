"""Fix round 088c: Raids page rankings key (BUG-002), mechanic miss wording (live F1), cohort realm
match (live F2) and links in note prose (SEC-002)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.agent_tools.mechanics import get_boss_mechanics
from backend.app.services import raid_summary
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.tests.test_072_raid_summary import (
    BOSS, RANKED, get, own_character, rankings, ranked, summary_report, track,
)
from backend.tests.test_086_mechanics_notes import GOOD_NOTE, _load, _tier, _with
from backend.tests.test_benchmark import FIGHT, PLAYER_CODE, make_responder
from backend.tests.wcl_fakes import install
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key
from wcl_agent.tools.benchmark import compare_player_to_cohort
from wcl_agent.tools.report_tools import get_report_rankings

# --- BUG-002: the Raids page finds whole-report rankings stored under an earlier fight list ------


def _with_encounters(code: str, ids: list[int]) -> dict:
    """The stored summary with encounter fights ``ids`` (BOSS first) and one trash fight."""
    report = summary_report(code)
    boss, trash = report["fights"]
    report["fights"] = [{**boss, "id": i, "startTime": 10 + i} for i in ids] + [trash]
    return report


def _summary_row(code: str, ids: list[int], at: datetime) -> FetchedResponse:
    body = json.dumps({"data": {"reportData": {"report": _with_encounters(code, ids)}}}).encode()
    return FetchedResponse(_flight_key(REPORT_SUMMARY, {"code": code}), REPORT_SUMMARY, {"code": code}, body, at)


async def _rankings_query(monkeypatch, code: str, ids: list[int]) -> tuple[str, dict]:
    """The whole-report rankings request get_report_rankings sends while the report has ``ids``."""
    def respond(query: str, variables: dict) -> dict:
        body = _with_encounters(code, ids) if query == REPORT_SUMMARY else {"rankings": rankings(*RANKED)}
        return {"data": {"reportData": {"report": body}}}

    fake = install(monkeypatch, respond)
    await get_report_rankings(code)
    [(query, variables)] = [(q, v) for q, v in fake.calls if "rankings(" in q]
    assert variables["fightIDs"] == ids
    return query, variables


def _rankings_row(code: str, query: str, ids: list[int], percent: float, at: datetime) -> FetchedResponse:
    variables = {"code": code, "fightIDs": ids}
    body = {"data": {"reportData": {"report": {"rankings": rankings(ranked("Thrall", "Tarren Mill", "EU", percent))}}}}
    return FetchedResponse(_flight_key(query, variables), query, variables, json.dumps(body).encode(), at)


@pytest.fixture
def payload_reads(monkeypatch) -> list[list[str]]:
    """The keys of each read_visible_parts call that read stored bodies (not just stamps)."""
    calls: list[list[str]] = []
    real = raid_summary.read_visible_parts

    async def spy(session, code, query_keys, paths, **kw):
        if paths:
            calls.append(list(query_keys))
        return await real(session, code, query_keys, paths, **kw)

    monkeypatch.setattr(raid_summary, "read_visible_parts", spy)
    return calls


def _whole_rankings_read(code: str, ranked_ids: list[int], reads: list[list[str]]) -> list[str]:
    whole = {k for k, kind in raid_summary.part_keys(code, [], ranked_ids).items() if kind == "whole_rankings"}
    return [k for call in reads for k in call if k in whole]


async def test_parses_stored_mid_raid_survive_a_newer_summary_with_more_pulls(as_user, patched_db, monkeypatch,
                                                                                payload_reads):
    """BUG-002: rankings asked after 2 pulls; the newest summary has 3. The parse still shows."""
    code = uuid.uuid4().hex[:16]
    query, _ = await _rankings_query(monkeypatch, code, [BOSS, 3])
    now = datetime.now(UTC)
    await store_batch([PendingWrite(r, as_user.tenant_id) for r in [
        _rankings_row(code, query, [BOSS, 3], 87.4, now - timedelta(minutes=10)),
        _summary_row(code, [BOSS, 3, 5], now),
    ]])
    await track(patched_db, as_user.tenant_id, code)
    await own_character(patched_db, as_user.tenant_id)

    body = (await get(as_user, code)).json()
    assert [p["percentile"] for p in body["my_characters"][0]["parses"]] == [87.4]


@pytest.mark.parametrize("newest", [[BOSS, 3], [BOSS, 3, 5]])
async def test_only_the_newest_whole_report_rankings_row_is_read(as_user, patched_db, monkeypatch, payload_reads,
                                                                 newest):
    """Bound: of the rows under earlier fight lists, one body is read (the newest), whatever its list."""
    code = uuid.uuid4().hex[:16]
    query, _ = await _rankings_query(monkeypatch, code, [BOSS, 3])
    now = datetime.now(UTC)
    lists = ([BOSS, 3], [BOSS, 3, 5])
    rows = [_rankings_row(code, query, ids, 90.0 if ids == newest else 10.0,
                          now - timedelta(minutes=1 if ids == newest else 20)) for ids in lists]
    await store_batch([PendingWrite(r, as_user.tenant_id) for r in [*rows, _summary_row(code, [BOSS, 3, 5], now)]])
    await track(patched_db, as_user.tenant_id, code)
    await own_character(patched_db, as_user.tenant_id)

    body = (await get(as_user, code)).json()
    assert [p["percentile"] for p in body["my_characters"][0]["parses"]] == [90.0]
    assert _whole_rankings_read(code, [BOSS, 3, 5], payload_reads) == [_flight_key(query, {"code": code,
                                                                                          "fightIDs": newest})]


async def test_a_long_report_still_reads_one_whole_report_rankings_body(as_user, patched_db, monkeypatch,
                                                                        payload_reads):
    """Volume at the bound: 200 pulls in the newest summary, rankings stored at 3 points of the night."""
    code = uuid.uuid4().hex[:16]
    ids = [BOSS, *range(3, 202)]
    query, _ = await _rankings_query(monkeypatch, code, ids[:2])
    now = datetime.now(UTC)
    rows = [_rankings_row(code, query, ids[:n], n / 2, now - timedelta(minutes=300 - n)) for n in (2, 50, 120)]
    await store_batch([PendingWrite(r, as_user.tenant_id) for r in [*rows, _summary_row(code, ids, now)]])
    await track(patched_db, as_user.tenant_id, code)
    await own_character(patched_db, as_user.tenant_id)

    body = (await get(as_user, code)).json()
    assert [p["percentile"] for p in body["my_characters"][0]["parses"]] == [60.0]
    assert len(_whole_rankings_read(code, ids, payload_reads)) == 1


# --- live F1: a miss on the asked boss says outright whose mechanic it is ----------------------


async def test_a_mechanic_of_another_boss_says_it_is_not_the_asked_bosses():
    result = await get_boss_mechanics("Gravebound", "Nekzali")
    assert result == {
        "status": "success",
        "found": False,
        "message": "Gravebound is not a Nek'zali the Soulcoiler mechanic in my guides; it is The Coiled Altar's. "
                   "Tell the user which boss it belongs to.",
        "found_under": ["The Coiled Altar"],
    }


async def test_a_boss_the_notes_lack_still_names_the_owner_and_never_echoes_the_argument():
    result = await get_boss_mechanics("Gravebound", "Mysterious Zzyzx")
    assert result["message"].startswith("Gravebound is not that boss's mechanic in my guides; it is The Coiled Altar's.")
    assert "Zzyzx" not in str(result)


# --- live F2: the cohort compare matches the player's realm however WCL spells it ---------------


async def test_the_cohort_finds_a_ranking_row_whose_realm_keeps_the_space_the_actor_drops(monkeypatch):
    """Live: actor server "Twilight'sHammer", ranking server "Twilight's Hammer" (live-check:088-pre)."""
    base = make_responder()

    def responder(query, variables):
        body = base(query, variables)
        if "rankings(fightIDs" in query:
            report = body["data"]["reportData"]["report"]
            for actor in report["masterData"]["actors"]:
                actor["server"] = "Twilight'sHammer"
            report["rankings"]["data"][0]["roles"]["dps"]["characters"][0]["server"] = {"name": "Twilight's Hammer"}
        return body

    install(monkeypatch, responder)
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    assert res["status"] in ("success", "limited"), res
    assert res["player"]["source_id"] == 7


async def test_the_cohort_still_rejects_a_namesake_on_another_realm(monkeypatch):
    base = make_responder()

    def responder(query, variables):
        body = base(query, variables)
        if "rankings(fightIDs" in query:
            body["data"]["reportData"]["report"]["rankings"]["data"][0]["roles"]["dps"]["characters"][0]["server"] = {
                "name": "Azshara Two"}
        return body

    install(monkeypatch, responder)
    res = await compare_player_to_cohort(PLAYER_CODE, FIGHT, "Hrslkks")
    assert res["status"] == "error" and "no ranking row" in res["error_message"]


# --- SEC-002: a link lives only in Source.url ----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["See https://evil.example/x for more.", "Read www.evil.example first.", "Guide at evil.example/path now.",
     "Mirror hxxp://evil.example/x here.", "Fullwidth evil．example link."],
)
@pytest.mark.parametrize("field", [("what_to_do",), ("what_it_does",), ("source", "name")])
def test_a_link_in_a_prose_field_keeps_the_tier_file_from_loading(tmp_path, text, field):
    with pytest.raises(ValidationError, match="link in prose"):
        _load(tmp_path, _tier(_with(field, text)))


def test_the_tier_note_rejects_a_link_too_and_plain_prose_with_dots_loads(tmp_path):
    tier = _tier(GOOD_NOTE)
    tier["note"] = "Patch notes at evil.example."
    with pytest.raises(ValidationError, match="link in prose"):
        _load(tmp_path, tier)
    plain = _with(("what_to_do",), "Soak at 2.5 seconds, e.g. with a defensive. Then move.")
    assert _load(tmp_path, _tier(plain))
