"""Stored raid summary API (feature 072, backend half of sc-142; board contract:raid-summary).

The stored rows are made by running our own tools against a fake Warcraft Logs client and storing
exactly the requests they sent, so the contract test also pins the store keys the endpoint reads.
Over SQLite; both raw-store reads on Postgres are in test_072_raid_summary_pg.py.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.auth import dependencies
from backend.app.db import repository as repo
from backend.app.db.models import UserCharacter
from backend.app.services import raid_summary
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.tests.wcl_fakes import install
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key
from wcl_agent.tools.participants import get_report_participants
from wcl_agent.tools.report_tools import get_report_rankings, load_report_table

# The board's contract example, verbatim.
CONTRACT = {
    "report_code": "a1B2c3D4e5F6g7H8",
    "has_data": True,
    "duration_ms": 9876000,
    "participants": [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement", "role": "dps"}],
    "my_characters": [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement",
                       "parses": [{"encounter": "Ulgrax the Devourer", "difficulty": "Heroic", "percentile": 87.4}]}],
    "fetched_at": "2026-11-07T19:00:00Z",
}
BOSS = 1  # the boss fight's id in the stored summary


def new_code() -> str:
    return uuid.uuid4().hex[:16]


def summary_report(code: str, *, visibility: str = "unlisted", actors=(("Thrall", "Shaman"),), ended=None) -> dict:
    end = ended or int((datetime.now(UTC) - timedelta(days=2)).timestamp() * 1000)
    return {
        "code": code, "visibility": visibility, "title": "Raid", "startTime": end - 9_876_000, "endTime": end,
        "zone": {"id": 42, "name": "Nerub-ar Palace"}, "guild": {"name": "G"},
        "masterData": {"actors": [{"id": i, "name": n, "subType": c} for i, (n, c) in enumerate(actors)]},
        "fights": [
            {"id": BOSS, "name": "Ulgrax the Devourer", "encounterID": 2902, "difficulty": 4, "kill": True,
             "size": 20, "startTime": 10, "friendlyPlayers": [0]},
            {"id": 2, "name": "Trash", "encounterID": 0, "difficulty": None, "kill": None, "startTime": 20},
        ],
    }


def player(name: str, realm: str, klass: str, spec: str) -> dict:
    return {"name": name, "server": realm, "type": klass, "specs": [{"spec": spec, "count": 1}]}


def ranked(name: str, realm: str, region: str, percent, spec: str = "Enhancement") -> dict:
    return {"name": name, "server": {"name": realm, "region": region}, "class": "Shaman", "spec": spec,
            "rankPercent": percent}


def rankings(*characters: dict) -> dict:
    return {"data": [{"fightID": BOSS, "encounter": {"id": 2902, "name": "Ulgrax the Devourer"}, "difficulty": 4,
                      "kill": True, "roles": {"dps": {"name": "DPS", "characters": list(characters)}}}]}


DPS = [player("Thrall", "Tarren Mill", "Shaman", "Enhancement")]
RANKED = [ranked("Thrall", "Tarren Mill", "EU", 87.4)]


async def stored_by_tools(monkeypatch, code: str, *, dps=DPS, ranked_rows=RANKED) -> list[FetchedResponse]:
    """Run our tools for ``code`` against a fake WCL and return what each request would store."""
    details = {"tanks": [], "healers": [], "dps": dps}

    def respond(query: str, variables: dict) -> dict:
        if "rankings(" in query:
            report = {"rankings": rankings(*ranked_rows)}
        elif "table(" in query:
            report = {"table": {"data": {"playerDetails": details, "composition": []}}}
        else:
            report = {"endTime": 1, "region": {"slug": "eu"}, "playerDetails": {"data": {"playerDetails": details}}}
        return {"data": {"reportData": {"report": report}}}

    real = wcl_client.get_async_client
    fake = install(monkeypatch, respond)
    await get_report_participants(code)
    await get_report_rankings(code)
    await get_report_rankings(code, fight_id=BOSS)
    await load_report_table(code, "Summary", fight_id=BOSS)
    now = datetime.now(UTC)
    rows = [
        FetchedResponse(_flight_key(q, v), q, v, json.dumps(respond(q, v)).encode(), now) for q, v in fake.calls
    ]
    monkeypatch.setattr(wcl_client, "get_async_client", real)  # the endpoint must not reach the fake
    return rows


def summary_row(code: str, at: datetime | None = None, **kw) -> FetchedResponse:
    body = json.dumps({"data": {"reportData": {"report": summary_report(code, **kw)}}}).encode()
    return FetchedResponse(_flight_key(REPORT_SUMMARY, {"code": code}), REPORT_SUMMARY, {"code": code}, body,
                           at or datetime.now(UTC))


async def track(factory, tenant: uuid.UUID, code: str) -> None:
    async with factory() as db:
        await repo.upsert_tracked_raid(db, tenant_id=tenant, report_code=code, label=code)
        await db.commit()


async def own_character(factory, tenant: uuid.UUID, name="Thrall", server="tarren-mill", region="EU") -> None:
    async with factory() as db:
        db.add(UserCharacter(tenant_id=tenant, role="self", name=name, server=server, region=region,
                             class_name="Shaman", active_spec="Enhancement"))
        await db.commit()


def shape(value):
    """Keys and JSON types, recursively (lists by their first element)."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return "number" if isinstance(value, (int, float)) and not isinstance(value, bool) else type(value).__name__


def refuse(query, variables):
    raise RuntimeError(f"WCL refused: {query[:60]}")


async def get(authed, code: str, params: dict | None = None):
    return await authed.client.get(f"/api/raids/{code}/summary", params=params)


# --- The contract ------------------------------------------------------------------------------


async def test_a_seeded_raid_answers_in_the_contract_shape(as_user, patched_db, monkeypatch):
    code = new_code()
    rows = await stored_by_tools(monkeypatch, code)
    await store_batch([PendingWrite(r, as_user.tenant_id) for r in [summary_row(code), *rows]])
    await track(patched_db, as_user.tenant_id, code)
    await own_character(patched_db, as_user.tenant_id)

    resp = await get(as_user, code)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert shape(body) == shape(CONTRACT)
    assert {k: v for k, v in body.items() if k != "fetched_at"} == {
        **{k: v for k, v in CONTRACT.items() if k != "fetched_at"}, "report_code": code,
    }
    assert datetime.fromisoformat(body["fetched_at"]) > datetime.now(UTC) - timedelta(minutes=5)


async def test_nothing_usable_stored_is_has_data_false(as_user, patched_db, monkeypatch):
    code = new_code()
    await track(patched_db, as_user.tenant_id, code)
    fake = install(monkeypatch, refuse)
    resp = await get(as_user, code)
    assert fake.calls == []  # nothing stored: nothing to re-verify
    assert resp.status_code == 200
    assert resp.json() == {"report_code": code, "has_data": False, "duration_ms": None, "participants": [],
                           "my_characters": [], "fetched_at": None}


async def test_each_part_may_be_missing_alone(as_user, patched_db, monkeypatch):
    only_summary, only_details = new_code(), new_code()
    details = [r for r in await stored_by_tools(monkeypatch, only_details) if "rankings(" not in r.query]
    await store_batch([PendingWrite(summary_row(only_summary), as_user.tenant_id),
                       *(PendingWrite(r, as_user.tenant_id) for r in details)])
    for c in (only_summary, only_details):
        await track(patched_db, as_user.tenant_id, c)
    await own_character(patched_db, as_user.tenant_id)

    a = (await get(as_user, only_summary)).json()
    assert a["has_data"] and a["duration_ms"] == 9_876_000
    assert a["participants"] == [{"name": "Thrall", "class_name": "Shaman", "spec": None, "role": None}]
    assert a["my_characters"] == [{"name": "Thrall", "class_name": "Shaman", "spec": None, "parses": []}]

    b = (await get(as_user, only_details)).json()
    assert b["has_data"] and b["duration_ms"] is None and b["fetched_at"] is not None
    assert b["participants"] == [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement", "role": "dps"}]
    assert b["my_characters"][0]["parses"] == []


async def test_a_visible_raid_makes_no_warcraft_logs_request(as_user, patched_db, monkeypatch):
    code = new_code()
    rows = await stored_by_tools(monkeypatch, code)
    await store_batch([PendingWrite(r, as_user.tenant_id) for r in [summary_row(code), *rows]])
    await track(patched_db, as_user.tenant_id, code)

    fake = install(monkeypatch, refuse)
    resp = await get(as_user, code)
    assert resp.status_code == 200 and resp.json()["has_data"]
    assert fake.calls == []


# --- Hostile inputs ----------------------------------------------------------------------------


async def test_another_workspaces_tracked_raid_is_404_and_leaks_nothing(as_user, make_authed_client, patched_db,
                                                                        monkeypatch):
    other = await make_authed_client("other@example.com")
    try:
        code = new_code()
        rows = await stored_by_tools(monkeypatch, code, dps=[player("Secretname", "Draenor", "Mage", "Fire")])
        await store_batch([PendingWrite(r, other.tenant_id) for r in [summary_row(code), *rows]])
        await track(patched_db, other.tenant_id, code)
        assert (await get(other, code)).json()["participants"]  # the owner sees it

        fake = install(monkeypatch, refuse)
        resp = await get(as_user, code)
        assert resp.status_code == 404
        assert resp.json() == {"detail": "not_found"}
        assert fake.calls == []
        assert "Secretname" not in resp.text
    finally:
        await other.client.aclose()


async def test_a_stored_public_report_the_workspace_does_not_track_is_404(as_user, patched_db, monkeypatch):
    code = new_code()
    rows = await stored_by_tools(monkeypatch, code)
    await store_batch([PendingWrite(r) for r in [summary_row(code, visibility="public"), *rows]])
    resp = await get(as_user, code)
    assert resp.status_code == 404
    assert "Thrall" not in resp.text


async def test_rows_granted_only_to_another_workspace_are_not_used_unless_wcl_serves_us(as_user, make_authed_client, patched_db,
                                                                   monkeypatch):
    """Both workspaces track the raid; only the other one fetched it (a grant, not public). The
    re-verify asks WCL once; it refuses, so nothing of the other workspace's rows is used."""
    other = await make_authed_client("other@example.com")
    try:
        code = new_code()
        rows = await stored_by_tools(monkeypatch, code)
        await store_batch([PendingWrite(r, other.tenant_id) for r in [summary_row(code), *rows]])
        for t in (as_user.tenant_id, other.tenant_id):
            await track(patched_db, t, code)
        await own_character(patched_db, as_user.tenant_id)

        assert (await get(other, code)).json()["has_data"]
        fake = install(monkeypatch, refuse)  # WCL won't serve it to us (private, or down)
        body = (await get(as_user, code)).json()
        assert len(fake.calls) == 1
        assert body == {"report_code": code, "has_data": False, "duration_ms": None, "participants": [],
                        "my_characters": [], "fetched_at": None}
    finally:
        await other.client.aclose()


@pytest.mark.parametrize("path_code", [
    "..%2F..%2Fapi", "a%5Cb", "abc%0A", "abc%0Adef", "A" * 300, "a" * 33,
    "%D0%B0bc",  # Cyrillic a
    "%EF%BC%A1%EF%BC%A2",  # full-width AB
    "abc%00", "abc%20",
])
async def test_a_report_code_with_path_tricks_is_404_before_any_query(as_user, monkeypatch, path_code):
    def no_transaction(*args, **kwargs):
        raise AssertionError("tenant transaction opened")

    async def no_summary(*args, **kwargs):
        raise AssertionError("summary read")

    monkeypatch.setattr(dependencies, "tenant_session", no_transaction)
    monkeypatch.setattr(raid_summary, "summarize", no_summary)
    resp = await as_user.client.get(f"/api/raids/{path_code}/summary")
    assert resp.status_code in (404, 422), resp.text


async def test_uploader_text_comes_back_cleaned_and_capped(as_user, patched_db, monkeypatch):
    code = new_code()
    long_name = "\x1b[31m<script>alert(1)</script>\x00" + "N" * 5000
    hostile_spec = "&lt;img src=x&gt;\u200bspec\x07"
    rows = await stored_by_tools(monkeypatch, code, dps=[player(long_name, "Tarren Mill", "Shaman", hostile_spec)])
    many = tuple((f"P{i}", "Warrior") for i in range(300))
    await store_batch([PendingWrite(r, as_user.tenant_id) for r in [summary_row(code, actors=many), *rows]])
    await track(patched_db, as_user.tenant_id, code)

    body = (await get(as_user, code)).json()

    assert len(body["participants"]) == raid_summary.MAX_PARTICIPANTS
    first = body["participants"][0]
    texts = [first["name"], first["spec"]]
    assert all(len(t) <= 60 for t in texts)
    assert not any(unicodedata.category(c) in ("Cc", "Cf") for t in texts for c in t)
    assert not any(c in t for t in texts for c in "<>")
    assert first["name"].startswith("[31m(script)alert(1)(/script)NNN") and first["name"].endswith("…")


async def test_my_characters_come_from_the_profile_matched_by_name_realm_and_region(as_user, patched_db,
                                                                                     monkeypatch):
    """A namesake on another realm, or on the same realm name in another region, isn't mine; a
    name in the query string changes nothing."""
    code = new_code()
    dps = [player("Thrall", "Draenor", "Shaman", "Elemental"), player("Thrall", "Tarren Mill", "Shaman", "Enhancement"),
           player("Jaina", "Tarren Mill", "Mage", "Frost")]
    ranks = [ranked("Thrall", "Draenor", "EU", 99.0, "Elemental"), ranked("Thrall", "Tarren Mill", "US", 98.0),
             ranked("Thrall", "Tarren Mill", "EU", 50.5)]
    rows = await stored_by_tools(monkeypatch, code, dps=dps, ranked_rows=ranks)
    await store_batch([PendingWrite(r, as_user.tenant_id) for r in [summary_row(code), *rows]])
    await track(patched_db, as_user.tenant_id, code)
    await own_character(patched_db, as_user.tenant_id)

    body = (await get(as_user, code, {"name": "Jaina", "character": "Jaina", "realm": "Draenor"})).json()

    assert body["my_characters"] == [{
        "name": "Thrall", "class_name": "Shaman", "spec": "Enhancement",
        "parses": [{"encounter": "Ulgrax the Devourer", "difficulty": "Heroic", "percentile": 50.5}],
    }]
    assert len([p for p in body["participants"] if p["name"] == "Thrall"]) == 2


# --- Re-verify (decision:072-reverify) ----------------------------------------------------------


async def stale_raid(monkeypatch, patched_db, tenant: uuid.UUID) -> str:
    """A tracked raid whose rows were fetched (and granted) three days ago: outside the window."""
    code = new_code()
    old = datetime.now(UTC) - timedelta(days=3)
    rows = [dataclasses.replace(r, fetched_at=old) for r in await stored_by_tools(monkeypatch, code)]
    await store_batch([PendingWrite(r, tenant) for r in [summary_row(code, at=old), *rows]])
    await track(patched_db, tenant, code)
    return code


async def test_a_stale_raid_is_reverified_with_one_summary_request(as_user, patched_db, monkeypatch):
    code = await stale_raid(monkeypatch, patched_db, as_user.tenant_id)
    install(monkeypatch, refuse)
    assert (await get(as_user, code)).json()["has_data"] is False  # WCL refused: nothing served
    raid_summary._reverified.clear()  # past the cooldown

    fake = install(monkeypatch, lambda q, v: {"data": {"reportData": {"report": summary_report(code)}}})
    body = (await get(as_user, code)).json()

    assert body["has_data"] and body["participants"][0]["spec"] == "Enhancement"  # stored parts served too
    assert fake.calls == [(REPORT_SUMMARY, {"code": code})]
    again = (await get(as_user, code)).json()
    assert again == body and len(fake.calls) == 1  # confirmed now: read straight from the store


@pytest.mark.parametrize("answer", [
    {"data": {"reportData": {"report": None}}},  # gone
    {"data": {"reportData": {"report": {"code": "SomeOtherCode1", "visibility": "public"}}}},
    {"errors": [{"message": "You do not have permission to view this report."}]},
])
async def test_a_reverify_that_wcl_does_not_answer_with_the_report_serves_nothing(as_user, patched_db, monkeypatch,
                                                                                 answer):
    code = await stale_raid(monkeypatch, patched_db, as_user.tenant_id)
    install(monkeypatch, lambda q, v: answer)
    body = (await get(as_user, code)).json()
    assert body["has_data"] is False and body["participants"] == []


async def test_a_slow_wcl_times_out_and_a_repeat_within_the_cooldown_sends_nothing(as_user, patched_db,
                                                                                   monkeypatch):
    code = await stale_raid(monkeypatch, patched_db, as_user.tenant_id)
    monkeypatch.setattr(raid_summary, "REVERIFY_TIMEOUT_S", 0.2)

    async def slow(query, variables):
        await asyncio.sleep(5)
        return {"data": {"reportData": {"report": summary_report(code)}}}

    fake = install(monkeypatch, slow)
    started = time.monotonic()
    assert (await get(as_user, code)).json()["has_data"] is False
    assert time.monotonic() - started < 3
    assert (await get(as_user, code)).json()["has_data"] is False
    assert len(fake.calls) == 1
