"""The stored-reports lookup is strict and cheap (feature 047, sc-324).

Only rows of our own summary queries with exact codes are used: a hand-written query named like
ours, a row with inexact codes and a row of another operation are never returned. Each returned
summary is cut down to the fields the lookup reads. Over SQLite; the Postgres index plan and the
statement timeout are in test_047_stored_reports_pg.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.app.agent_tools.stored_data_tools import NOT_STORED, list_stored_reports_for_character
from backend.app.db import repository as repo
from backend.app.db.models import RawFetch
from backend.app.repositories.raw_fetches import (
    ReportStatus,
    _payload,
    list_visible_summaries,
    record_report_status,
)
from backend.app.services.fetch_persistence import PendingWrite, store_batch
from backend.app.tenancy.context import RequestIdentity, current_identity
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

NOW = datetime.now(UTC)
SINCE = NOW - timedelta(days=1)
ENDED = int((NOW - timedelta(days=3)).timestamp() * 1000)
# A hand-written query (run_wcl_graphql) that borrows our operation name.
FORGED = (
    "query ReportSummary($code: String!) { reportData { report(code: $code) "
    "{ code title startTime zone { name } masterData { actors { name } } } } }"
)


def report(code: str, actors=("Vagxsu",), start: int = 1) -> dict:
    return {
        "code": code, "visibility": "unlisted", "title": f"Raid {code}", "startTime": start, "endTime": ENDED,
        "zone": {"id": 46, "name": "The Venomous Abyss"}, "guild": {"name": "G"},
        "masterData": {"actors": [{"id": 7 + i, "name": n, "subType": "Warrior"} for i, n in enumerate(actors)]},
        "fights": [{"id": i, "name": "Boss", "encounterID": 3101, "difficulty": 5, "kill": True, "size": 20,
                    "startTime": i, "friendlyPlayers": [7]} for i in range(50)],
    }


def fetched(query: str, variables: dict, data: dict) -> FetchedResponse:
    body = json.dumps({"data": {"_cost": {"pointsSpentThisHour": 1}, **data}}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, NOW)


async def listed(factory, tenant: uuid.UUID) -> list[dict]:
    async with factory() as session:
        bodies = await list_visible_summaries(session, tenant_id=tenant, since=SINCE, limit=200)
    return [json.loads(b) for b in bodies]


def codes_of(bodies: list[dict]) -> set[str]:
    return {r["code"] for b in bodies for r in ((b["data"] or {}).get("reportData") or {}).values()}


async def insert_row(
    factory, key: str, op: str, params: dict, codes: list[str], data: dict, fetched_at: datetime = NOW
) -> None:
    """A stored row as it may sit in the table (written by an older or looser path)."""
    async with factory() as session:
        body = json.dumps({"data": data})
        await session.execute(
            RawFetch.__table__.insert().values(
                query_key=key, operation_name=op, params=params, report_code=None, report_codes=codes,
                fetched_at=fetched_at, payload=_payload("sqlite", body), payload_hash=None,
            )
        )
        await record_report_status(session, [ReportStatus(c, "public", ENDED, NOW) for c in codes])
        await session.commit()


async def test_our_single_and_batch_summaries_are_listed(patched_db, tenant_id):
    batch = fetched(report_summaries_query(2), {"c0": "Ok2", "c1": "Ok3"},
                    {"reportData": {"r0": report("Ok2"), "r1": report("Ok3")}})
    await store_batch([
        PendingWrite(fetched(REPORT_SUMMARY, {"code": "Ok1"}, {"reportData": {"report": report("Ok1")}}), tenant_id),
        PendingWrite(batch, tenant_id),
    ])
    assert codes_of(await listed(patched_db, tenant_id)) == {"Ok1", "Ok2", "Ok3"}


async def test_a_hand_written_query_named_like_ours_is_never_listed(patched_db, tenant_id):
    async with patched_db() as session:
        await repo.upsert_known_player(session, tenant_id=tenant_id, name="Vagxsu", server="Tarren Mill", region="EU")
        await session.commit()
    forged = fetched(FORGED, {"code": "Fg1"}, {"reportData": {"report": report("Fg1")}})
    await store_batch([PendingWrite(forged, tenant_id)])  # granted: the body holds the report
    async with patched_db() as session:
        assert (await session.get(RawFetch, forged.query_key)).operation_name == "ReportSummary"
    assert await listed(patched_db, tenant_id) == []
    token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant_id, "member", False, uuid.uuid4()))
    try:
        out = await list_stored_reports_for_character("Vagxsu", tool_context=SimpleNamespace(user_id=str(tenant_id)))
    finally:
        current_identity.reset(token)
    assert out == NOT_STORED


async def test_a_row_with_inexact_codes_is_never_listed(patched_db, tenant_id):
    params = {"code": "Ix1"}
    # Our query's key, but the row names a code the params don't give (loose, 041 BUG-007 style).
    await insert_row(patched_db, _flight_key(REPORT_SUMMARY, params), "ReportSummary", params, ["Ix1", "Ix2"],
                     {"reportData": {"report": report("Ix1")}})
    # A padded code is never exact (041 BUG-003), whatever the key.
    padded = {"code": "Ix3 "}
    await insert_row(patched_db, _flight_key(REPORT_SUMMARY, padded), "ReportSummary", padded, ["Ix3"],
                     {"reportData": {"report": report("Ix3")}})
    assert await listed(patched_db, tenant_id) == []


async def test_a_row_of_another_operation_is_never_listed(patched_db, tenant_id):
    params = {"code": "Op1"}
    await insert_row(patched_db, _flight_key(REPORT_SUMMARY, params), "ReportQ", params, ["Op1"],
                     {"reportData": {"report": report("Op1")}})
    assert await listed(patched_db, tenant_id) == []


async def test_only_the_needed_fields_come_back(patched_db, tenant_id):
    full = fetched(REPORT_SUMMARY, {"code": "Pj1"}, {"reportData": {"report": report("Pj1", ("Vagxsu", "Other"))}})
    await store_batch([PendingWrite(full, tenant_id)])
    [body] = await listed(patched_db, tenant_id)
    assert body == {"data": {"reportData": {"report": {
        "code": "Pj1", "title": "Raid Pj1", "startTime": 1, "zone": {"name": "The Venomous Abyss"},
        "masterData": {"actors": [{"name": "Vagxsu"}, {"name": "Other"}]},
    }}}}
    assert len(json.dumps(body)) * 10 < len(full.content)


async def test_the_scan_reads_only_rows_fetched_since_the_visibility_window(patched_db, tenant_id):
    """049 PERF-002: ``fetched_at >= since`` bounds the walk (the Postgres plan is in the _pg file)."""
    for code, at in (("Bd1", NOW), ("Bd2", SINCE - timedelta(hours=1))):
        params = {"code": code}  # both visible by a fresh public status; only the fetch time differs
        await insert_row(patched_db, _flight_key(REPORT_SUMMARY, params), "ReportSummary", params, [code],
                         {"reportData": {"report": report(code)}}, fetched_at=at)
    assert codes_of(await listed(patched_db, tenant_id)) == {"Bd1"}
