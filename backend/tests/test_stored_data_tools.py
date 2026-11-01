"""Exact lookups in stored data (feature 045, sc-131).

The three tools read through the 039 visibility rule only: a row the workspace may not see
answers exactly like one never stored. Seeded through the real writer over SQLite.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.agent_tools import stored_data_tools as sdt
from backend.app.agent_tools.stored_data_tools import (
    NOT_STORED,
    STORED_DATA_TOOLS,
    get_stored_fight_table,
    list_stored_fights,
    list_stored_reports_for_character,
)
from backend.app.db import repository as repo
from backend.app.services import name_resolver as nr
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests.wcl_fakes import install
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key
from wcl_agent.tools import report_tools

NOW = datetime.now(UTC)
ENDED = int((NOW - timedelta(days=3)).timestamp() * 1000)
FIGHTS = [
    {"id": 1, "name": "Ula'tek", "encounterID": 3101, "difficulty": 5, "kill": False, "size": 20,
     "startTime": 10, "friendlyPlayers": [7]},
    {"id": 2, "name": "Queen Ansurek", "encounterID": 3102, "difficulty": 5, "kill": True, "size": 20,
     "startTime": 20, "friendlyPlayers": [7]},
]


def body(data: dict) -> bytes:
    return json.dumps({"data": {"_cost": {"pointsSpentThisHour": 1}, **data}}).encode()


def summary(code: str, visibility: str = "unlisted", start: int = 1, actors=("Vagxsu",)) -> FetchedResponse:
    report = {
        "code": code, "visibility": visibility, "title": f"Raid {code}", "startTime": start, "endTime": ENDED,
        "zone": {"id": 46, "name": "The Venomous Abyss"}, "guild": {"name": "G"},
        "masterData": {"actors": [{"id": 7 + i, "name": n, "subType": "Warrior"} for i, n in enumerate(actors)]},
        "fights": FIGHTS,
    }
    variables = {"code": code}
    return FetchedResponse(_flight_key(REPORT_SUMMARY, variables), REPORT_SUMMARY, variables,
                           body({"reportData": {"report": report}}), NOW)


async def capture_table_request(monkeypatch, **kwargs) -> tuple[str, dict]:
    """The request get_report_table really sends: the key its stored answer has."""
    seen: list = []

    def responder(query, variables):
        seen.append((query, variables))
        return {"data": {"reportData": {"report": {"table": {"rows": [1]}, "endTime": ENDED}}}}

    install(monkeypatch, responder)
    await report_tools.get_report_table(**kwargs)
    return seen[0]


def table_row(query: str, variables: dict, table) -> FetchedResponse:
    return FetchedResponse(_flight_key(query, variables), query, variables,
                           body({"reportData": {"report": {"table": table}}}), NOW)


@contextlib.contextmanager
def turn(tenant: uuid.UUID):
    token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4()))
    try:
        yield SimpleNamespace(user_id=str(tenant))
    finally:
        current_identity.reset(token)


@pytest.fixture(autouse=True)
def zones(monkeypatch):
    async def load():
        return [{"id": 46, "name": "The Venomous Abyss",
                 "encounters": [{"id": 3101, "name": "Ula'tek"}, {"id": 3102, "name": "Queen Ansurek"}]}]

    monkeypatch.setattr(nr, "load_world_zones", load)


# --- list_stored_fights ----------------------------------------------------------------------


async def test_stored_fights_for_a_visible_report(patched_db, tenant_id):
    await store_batch([PendingWrite(summary("Fi1"), tenant_id)])
    with turn(tenant_id) as ctx:
        out = await list_stored_fights("Fi1", tool_context=ctx)
    assert out["status"] == "success" and out["title"] == "Raid Fi1" and not out["truncated"]
    assert out["fights"][1] == {"id": 2, "name": "Queen Ansurek", "encounter_id": 3102, "difficulty": 5,
                                "kill": True, "size": 20, "start_time_ms": 20}


async def test_an_encounter_argument_is_resolved_and_filters(patched_db, tenant_id):
    await store_batch([PendingWrite(summary("Fi2"), tenant_id)])
    with turn(tenant_id) as ctx:
        out = await list_stored_fights("Fi2", encounter="ansurek", tool_context=ctx)
        bad = await list_stored_fights("Fi2", encounter="Ulatekk", tool_context=ctx)
    assert [f["id"] for f in out["fights"]] == [2]
    assert bad["status"] == "error" and "Ula'tek" in bad["matches"]  # correctable


async def test_not_visible_and_not_stored_are_the_same_answer(patched_db, tenant_id, other_tenant_id):
    await store_batch([PendingWrite(summary("Hid1"), tenant_id)])  # granted to tenant A only
    with turn(other_tenant_id) as ctx:
        hidden = await list_stored_fights("Hid1", tool_context=ctx)
        absent = await list_stored_fights("Nope1", tool_context=ctx)
    assert hidden == absent == NOT_STORED
    assert json.dumps(hidden) == json.dumps(absent)


async def test_a_stale_live_report_is_not_stored(patched_db, tenant_id):
    live = summary("Live1")
    data = json.loads(live.content)
    data["data"]["reportData"]["report"]["endTime"] = int(NOW.timestamp() * 1000)  # still logging
    old = FetchedResponse(live.query_key, live.query, live.variables, json.dumps(data).encode(),
                          NOW - timedelta(hours=1))
    await store_batch([PendingWrite(old, tenant_id)])
    with turn(tenant_id) as ctx:
        assert await list_stored_fights("Live1", tool_context=ctx) == NOT_STORED


async def test_outside_an_authenticated_turn_the_tools_fail_closed(patched_db, tenant_id, other_tenant_id):
    await store_batch([PendingWrite(summary("Out1", "public"), tenant_id)])
    assert (await list_stored_fights("Out1", tool_context=SimpleNamespace(user_id="x")))["status"] == "error"
    with turn(tenant_id):  # an ADK session of another workspace
        wrong = SimpleNamespace(user_id=str(other_tenant_id))
        assert (await list_stored_fights("Out1", tool_context=wrong))["status"] == "error"
        assert (await list_stored_reports_for_character("Vagxsu", tool_context=wrong))["status"] == "error"


async def test_fights_are_capped(patched_db, monkeypatch, tenant_id):
    monkeypatch.setattr(sdt, "MAX_FIGHTS", 1)
    await store_batch([PendingWrite(summary("Cap1"), tenant_id)])
    with turn(tenant_id) as ctx:
        out = await list_stored_fights("Cap1", tool_context=ctx)
    assert len(out["fights"]) == 1 and out["truncated"]


# --- get_stored_fight_table ------------------------------------------------------------------


@pytest.mark.parametrize("source_id", [0, 7])
async def test_the_stored_table_is_the_one_get_report_table_fetched(patched_db, monkeypatch, tenant_id, source_id):
    query, variables = await capture_table_request(
        monkeypatch, report_code="Tb1", data_type="DamageDone", fight_id=2, source_id=source_id
    )
    await store_batch([PendingWrite(summary("Tb1")), PendingWrite(table_row(query, variables, {"rows": [42]}), tenant_id)])
    with turn(tenant_id) as ctx:
        out = await get_stored_fight_table("Tb1", "DamageDone", fight_id=2, source_id=source_id, tool_context=ctx)
        other_fight = await get_stored_fight_table("Tb1", "DamageDone", fight_id=1, source_id=source_id,
                                                   tool_context=ctx)
    assert out == {"status": "success", "data_type": "DamageDone", "table": {"rows": [42]}}
    assert other_fight == NOT_STORED


async def test_an_invisible_table_is_not_stored(patched_db, monkeypatch, tenant_id, other_tenant_id):
    query, variables = await capture_table_request(monkeypatch, report_code="Tb2", data_type="Healing")
    await store_batch([PendingWrite(summary("Tb2")), PendingWrite(table_row(query, variables, {"rows": [1]}), tenant_id)])
    with turn(other_tenant_id) as ctx:
        assert await get_stored_fight_table("Tb2", "Healing", tool_context=ctx) == NOT_STORED


async def test_a_bad_data_type_is_refused(tenant_id):
    with turn(tenant_id) as ctx:
        out = await get_stored_fight_table("Tb3", "Nope", tool_context=ctx)
    assert out["status"] == "error" and "DamageDone" in out["valid"]


async def test_a_large_table_is_capped_like_the_wcl_tool(patched_db, monkeypatch, tenant_id):
    query, variables = await capture_table_request(monkeypatch, report_code="Tb4", data_type="Casts")
    big = {"rows": [{"n": i, "pad": "x" * 200} for i in range(5000)]}
    await store_batch([PendingWrite(summary("Tb4")), PendingWrite(table_row(query, variables, big), tenant_id)])
    with turn(tenant_id) as ctx:
        out = await get_stored_fight_table("Tb4", "Casts", tool_context=ctx)
    assert out["status"] == "success" and len(json.dumps(out)) < len(json.dumps(big))


# --- list_stored_reports_for_character -------------------------------------------------------


async def test_reports_a_character_appears_in_newest_first(patched_db, tenant_id, other_tenant_id):
    async with patched_db() as session:
        await repo.upsert_known_player(session, tenant_id=tenant_id, name="Vagxsu", server="Tarren Mill", region="EU")
        await session.commit()
    await store_batch([
        PendingWrite(summary("Ch1", start=100), tenant_id),
        PendingWrite(summary("Ch2", start=200), tenant_id),
        PendingWrite(summary("Ch3", start=300, actors=("Someone",)), tenant_id),
        PendingWrite(summary("Ch4", start=400), other_tenant_id),  # not visible to A
    ])
    with turn(tenant_id) as ctx:
        out = await list_stored_reports_for_character("vagxsu", tool_context=ctx)
    assert out["status"] == "success" and out["character"] == "Vagxsu"
    assert [r["code"] for r in out["reports"]] == ["Ch2", "Ch1"]
    assert out["reports"][0] == {"code": "Ch2", "title": "Raid Ch2", "start_time_ms": 200,
                                 "zone": "The Venomous Abyss"}


async def test_an_unknown_character_is_a_correctable_error(patched_db, tenant_id):
    async with patched_db() as session:
        await repo.upsert_known_player(session, tenant_id=tenant_id, name="Vagxsu", server="Tarren Mill", region="EU")
        await session.commit()
    with turn(tenant_id) as ctx:
        out = await list_stored_reports_for_character("Vagxsy", tool_context=ctx)
    assert out["status"] == "error" and out["matches"] == ["Vagxsu"]


async def test_a_character_only_in_invisible_reports_is_not_stored(patched_db, tenant_id, other_tenant_id):
    async with patched_db() as session:
        await repo.upsert_known_player(session, tenant_id=other_tenant_id, name="Vagxsu", server="X", region="EU")
        await session.commit()
    await store_batch([PendingWrite(summary("Iv1"), tenant_id)])
    with turn(other_tenant_id) as ctx:
        assert await list_stored_reports_for_character("Vagxsu", tool_context=ctx) == NOT_STORED


# --- registration and the capability budget (#48) ---------------------------------------------


def test_the_tools_carry_the_contract_names():
    names = [t.__name__ for t in STORED_DATA_TOOLS.tools]
    assert names == ["list_stored_fights", "get_stored_fight_table", "list_stored_reports_for_character"]
    assert not STORED_DATA_TOOLS.note  # read-only: no can-change line


def test_the_real_groups_fit_the_capability_budget():
    from backend.app.agent_tools.profile_tools import PROFILE_TOOLS
    from wcl_agent.agent import build_agent
    from wcl_agent.capabilities import CAPABILITY_SUMMARY_MAX_CHARS, MAX_TOOL_LINE_CHARS

    groups = [PROFILE_TOOLS, STORED_DATA_TOOLS]
    with contextlib.suppress(ImportError):  # 044's group, once merged
        from backend.app.agent_tools.kb_tools import KB_TOOLS

        groups.append(KB_TOOLS)
    text = build_agent("gemini-3.6-flash", extra_groups=tuple(groups)).instruction(None)
    summary = text.split("<TOOLS>\n", 1)[1].split("</TOOLS>", 1)[0]
    assert len(summary) <= CAPABILITY_SUMMARY_MAX_CHARS
    assert all(len(line) <= MAX_TOOL_LINE_CHARS for line in summary.splitlines() if line.startswith("- "))
    assert "- list_stored_fights: " in summary
