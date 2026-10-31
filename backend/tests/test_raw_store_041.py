"""QA fix round 041 for the raw store (sprint 2026-10-31c QA: BUG-001..005/007, SEC-001..003,
SPEC-001/003/004, PERF-003/008). Decisions scope:041:gone-rule, :grant-rule, :writer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from backend.app.db.models import RawFetch, RawFetchGrant
from backend.app.services import fetch_persistence
from backend.app.services.fetch_persistence import FetchWriter, PendingWrite, store_batch
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.client import wcl_client
from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import FetchedResponse, ReportGone, _flight_key

NOW = datetime.now(UTC)
PLAIN_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { title } } }"
LOGGER = "backend.app.services.fetch_persistence"


def fetched(query: str, variables: dict, data: dict | None, extra: dict | None = None) -> FetchedResponse:
    body = json.dumps({"data": None if data is None else {"_cost": {"p": 1}, **data}, **(extra or {})}).encode()
    return FetchedResponse(_flight_key(query, variables), query, variables, body, NOW)


async def grants(patched_db) -> set[str]:
    async with patched_db() as session:
        return set(await session.scalars(select(RawFetchGrant.report_code)))


@pytest.fixture
def offered(monkeypatch) -> list:
    seen: list = []
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    wcl_client.set_fetch_sink(seen.append)
    return seen


async def answer(query: str, variables: dict, body: dict) -> None:
    client = mock_async_client(lambda request: gql_response(body))
    try:
        await client.query(query, variables)
    except RuntimeError:
        pass  # GraphQL errors still raise, as before
    finally:
        await client.aclose()


def gone(offered) -> list[ReportGone]:
    return [o for o in offered if isinstance(o, ReportGone)]


# --- Fix 1: gone only when WCL really says the report is gone ------------------------------


async def test_our_summary_answered_null_still_deletes(offered):
    await answer(REPORT_SUMMARY, {"code": "Gone1"}, {"data": {"reportData": {"report": None}}})
    await answer(REPORT_SUMMARY, {"code": "Gone2"}, {
        "data": {"reportData": {"report": None}},
        "errors": [{"message": "You do not have permission to view this report.", "path": ["reportData", "report"]}],
    })
    assert [g.codes for g in gone(offered)] == [("Gone1",), ("Gone2",)]


async def test_a_null_propagated_from_a_subfield_error_deletes_nothing(offered):
    await answer(REPORT_SUMMARY, {"code": "Alive1"}, {
        "data": {"reportData": {"report": None}},
        "errors": [{"message": "Internal server error", "path": ["reportData", "report", "fights", 0, "name"]}],
    })
    assert gone(offered) == []


async def test_a_transient_error_on_the_report_itself_deletes_nothing(offered):
    await answer(REPORT_SUMMARY, {"code": "Alive2"}, {
        "data": {"reportData": {"report": None}},
        "errors": [{"message": "Internal server error", "path": ["reportData", "report"]}],
    })
    assert gone(offered) == []


async def test_an_aliased_reportdata_key_deletes_nothing(offered):
    query = 'query { x: reportData { report(code: "Victim") { title } } reportData: guildData { report: guild(id: 1) { name } } }'
    await answer(query, {}, {"data": {"x": {"report": {"title": "Raid"}}, "reportData": {"report": None}}})
    assert gone(offered) == []


async def test_a_padded_code_deletes_nothing(offered):
    await answer('query { reportData { report(code: "ABC ") { title } } }', {}, {"data": {"reportData": {"report": None}}})
    await answer(REPORT_SUMMARY, {"code": "ABC "}, {"data": {"reportData": {"report": None}}})
    assert gone(offered) == []


async def test_a_hand_written_query_answered_null_deletes_nothing(offered):
    await answer(PLAIN_Q, {"code": "Alive3"}, {"data": {"reportData": {"report": None}}})
    assert gone(offered) == []


async def test_a_subfield_error_keeps_the_stored_rows_end_to_end(patched_db, monkeypatch, tenant_id):
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    await store_batch([PendingWrite(fetched(PLAIN_Q, {"code": "Kept1"}, {"reportData": {"report": {"title": "R"}}}), tenant_id)])
    writer = FetchWriter(max_items=10, max_bytes=1 << 20)
    writer.start()
    await answer(REPORT_SUMMARY, {"code": "Kept1"}, {
        "data": {"reportData": {"report": None}},
        "errors": [{"message": "boom", "path": ["reportData", "report", "title"]}],
    })
    await writer.stop()
    async with patched_db() as session:
        assert await session.scalar(select(func.count()).select_from(RawFetch)) == 1


async def test_an_unparsed_report_row_is_still_filed_under_its_codes(session):
    """BUG-007: a report the strict parser can't resolve is still found by delete-on-gone."""
    from backend.app.repositories.raw_fetches import delete_report, upsert_raw_fetch

    query = 'query { reportData { report(code: "A") { title } } x: reportData { report(fightIDs: [1], code: "B") { title } } }'
    await upsert_raw_fetch(session, fetched(query, {}, {"reportData": {}}))
    assert await delete_report(session, "B") == 1


# --- Fix 2: grants come from what WCL returned ---------------------------------------------


async def test_a_plain_query_that_returned_its_report_grants_it(patched_db, tenant_id):
    await store_batch([PendingWrite(fetched(PLAIN_Q, {"code": "Real1"}, {"reportData": {"report": {"title": "R"}}}), tenant_id)])
    assert await grants(patched_db) == {"Real1"}


@pytest.mark.parametrize(
    ("query", "variables", "data"),
    [
        pytest.param(  # a field skipped by a directive: WCL never resolved it
            "query Q($code: String!) { reportData { report(code: $code) @skip(if: true) { title } } }",
            {"code": "Skip1"}, {"reportData": {}}, id="skip-directive"),
        pytest.param(
            "query Q($code: String!) { reportData { report(code: $code) @include(if: false) { title } } }",
            {"code": "Incl1"}, {"reportData": {"report": {"title": "x"}}}, id="include-directive"),
        pytest.param(  # the code sits inside a string literal of another field
            'query Q($code: String!) { reportData { report(code: $code) { title } } '
            'characterData { character(name: """report(code: "Victim")""", serverSlug: "x", serverRegion: "us") { id } } }',
            {"code": "Mine1"}, {"reportData": {"report": {"title": "R"}}, "characterData": {"character": None}},
            id="string-literal"),
        pytest.param(  # aliased single report answered null, no errors
            "query Q($c: String!) { reportData { x: report(code: $c) { title } } }",
            {"c": "Alias1"}, {"reportData": {"x": None}}, id="alias-null"),
        pytest.param(  # aliased response key can't be trusted even when it holds an object
            "query Q($c: String!) { reportData: guildData { report: guild(id: 1) { name } } x: reportData { report(code: $c) { title } } }",
            {"c": "Alias2"}, {"reportData": {"report": {"name": "G"}}, "x": {"report": None}}, id="alias-forged"),
        pytest.param(  # a null single report padded above the old 4 KB gone-scan limit
            PLAIN_Q, {"code": "Big1"}, {"reportData": {"report": None}, "pad": "x" * 6000}, id="oversize-null"),
    ],
)
async def test_no_grant_unless_wcl_returned_the_report(patched_db, tenant_id, query, variables, data):
    await store_batch([PendingWrite(fetched(query, variables, data), tenant_id)])
    assert await grants(patched_db) == set()


async def test_a_batch_summary_grants_only_the_reports_that_came_back(patched_db, tenant_id):
    item = fetched(report_summaries_query(2), {"c0": "Back1", "c1": "Null1"}, {
        "reportData": {"r0": {"code": "Back1", "visibility": "unlisted", "endTime": 1}, "r1": None}})
    await store_batch([PendingWrite(item, tenant_id)])
    assert await grants(patched_db) == {"Back1"}


async def test_a_summary_whose_returned_code_differs_grants_nothing(patched_db, tenant_id):
    item = fetched(REPORT_SUMMARY, {"code": "Asked1"}, {"reportData": {"report": {"code": "Other", "visibility": "unlisted"}}})
    await store_batch([PendingWrite(item, tenant_id)])
    assert await grants(patched_db) == set()


# --- Fix 3: the writer's batch timeout, byte cap and eviction --------------------------------


def item(code: str, size: int = 0) -> PendingWrite:
    return PendingWrite(FetchedResponse(f"k-{code}", PLAIN_Q, {"code": code}, b"x" * size, NOW))


async def _hold_then(writer: FetchWriter, entered: asyncio.Event, release: asyncio.Event, items) -> None:
    writer.offer(FetchedResponse("k-hold", PLAIN_Q, {"code": "hold"}, b"", NOW))
    await entered.wait()
    for p in items:
        writer.offer(p.item)
    release.set()
    await writer.stop()


async def test_a_timed_out_batch_is_retried_item_by_item_and_keeps_its_report_gone(monkeypatch, caplog):
    monkeypatch.setattr(fetch_persistence, "_WRITE_TIMEOUT_S", 0.1)
    entered, release = asyncio.Event(), asyncio.Event()
    written: list[str] = []

    async def slow_batches(batch):
        names = [p.item.codes[0] if isinstance(p.item, ReportGone) else p.item.variables["code"] for p in batch]
        if names == ["hold"]:
            entered.set()
            await release.wait()
            return []
        if len(batch) > 1:
            await asyncio.sleep(1)  # the batch times out
        written.extend(names)
        return []

    writer = FetchWriter(slow_batches, max_items=50, max_bytes=1 << 20)
    writer.start()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await _hold_then(writer, entered, release,
                         [item("A"), PendingWrite(ReportGone(("Gone9",), NOW)), item("B")])
    assert written == ["A", "Gone9", "B"]  # nothing lost, order kept
    assert not [r for r in caplog.records if "write(s) failed" in r.getMessage()]


async def test_batches_are_capped_by_bytes(monkeypatch):
    monkeypatch.setattr(fetch_persistence, "BATCH_MAX_BYTES", 100)
    entered, release = asyncio.Event(), asyncio.Event()
    batches: list[list[str]] = []

    async def recording(batch):
        names = [p.item.variables["code"] for p in batch]
        if names == ["hold"]:
            entered.set()
            await release.wait()
            return []
        batches.append(names)
        return []

    writer = FetchWriter(recording, max_items=50, max_bytes=1 << 20)
    writer.start()
    await _hold_then(writer, entered, release, [item("A", 40), item("B", 40), item("C", 40), item("Big", 500), item("D", 10)])
    assert batches == [["A", "B"], ["C"], ["Big"], ["D"]]


async def test_redis_eviction_runs_outside_the_timed_db_part(monkeypatch, caplog):
    monkeypatch.setattr(fetch_persistence, "_WRITE_TIMEOUT_S", 0.05)
    evicted: list[str] = []

    async def slow_evict(code):
        await asyncio.sleep(0.2)  # longer than the DB timeout
        evicted.append(code)
        return 1

    async def store(batch):
        return [c for p in batch if isinstance(p.item, ReportGone) for c in p.item.codes]

    monkeypatch.setattr(fetch_persistence, "evict_report", slow_evict)
    writer = FetchWriter(store, max_items=10, max_bytes=1 << 20)
    writer.start()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        writer.offer(ReportGone(("Ev1",), NOW))
        await writer.stop()
    assert evicted == ["Ev1"]
    assert not [r for r in caplog.records if "failed" in r.getMessage()]
