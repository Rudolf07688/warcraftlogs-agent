"""The WCL client's fetch sink and its query helpers (feature 020, contracts/fetch-sink.md S1-S6)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import FetchedResponse, operation_name, report_codes

REPORT_Q = "query ReportQ($code: String!) { reportData { report(code: $code) { title } } }"
COST = {"limitPerHour": 3600, "pointsSpentThisHour": 12, "pointsResetIn": 900}


@pytest.fixture
def offered(monkeypatch) -> list[FetchedResponse]:
    """Install a recording sink; the module global is restored after the test."""
    seen: list[FetchedResponse] = []
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    wcl_client.set_fetch_sink(seen.append)
    return seen


async def test_a_successful_call_is_offered_once_with_its_raw_body(offered):
    async def handler(request):
        return gql_response({"data": {"_cost": COST, "reportData": {"report": {"title": "T"}}}})

    client = mock_async_client(handler)
    result = await client.query(REPORT_Q, {"code": "AbC1"})
    await client.aclose()

    assert result == {"data": {"reportData": {"report": {"title": "T"}}}}  # caller never sees _cost
    assert len(offered) == 1
    fetched = offered[0]
    assert fetched.query == REPORT_Q and fetched.variables == {"code": "AbC1"}
    assert fetched.query_key == wcl_client._flight_key(REPORT_Q, {"code": "AbC1"})
    assert b'"_cost"' in fetched.content  # stripped later, by the database
    assert fetched.fetched_at.tzinfo is not None


async def test_concurrent_identical_queries_are_offered_once(offered):
    async def handler(request):
        await asyncio.sleep(0.05)
        return gql_response({"data": {"value": 1}})

    client = mock_async_client(handler)
    await asyncio.gather(*(client.query(REPORT_Q, {"code": "SF"}) for _ in range(3)))
    await client.aclose()
    assert len(offered) == 1


async def test_failed_calls_are_never_offered(offered):
    responses = iter(
        [
            httpx.Response(400, content=b"bad request"),
            gql_response({"data": None, "errors": [{"message": "no such report"}]}),
        ]
    )
    client = mock_async_client(lambda request: next(responses))
    with pytest.raises(httpx.HTTPStatusError):
        await client.query(REPORT_Q, {"code": "X"})
    with pytest.raises(RuntimeError):
        await client.query(REPORT_Q, {"code": "Y"})
    await client.aclose()
    assert offered == []


async def test_no_sink_means_nothing_is_offered(monkeypatch):
    monkeypatch.setattr(wcl_client, "_fetch_sink", None)
    client = mock_async_client(lambda request: gql_response({"data": {"value": 1}}))
    assert await client.query(REPORT_Q, {"code": "X"}) == {"data": {"value": 1}}
    await client.aclose()


async def test_a_raising_sink_never_fails_the_fetch(monkeypatch):
    def broken(fetched):
        raise RuntimeError("sink down")

    monkeypatch.setattr(wcl_client, "_fetch_sink", broken)
    client = mock_async_client(lambda request: gql_response({"data": {"value": 2}}))
    assert await client.query(REPORT_Q, {"code": "X"}) == {"data": {"value": 2}}
    await client.aclose()


def test_the_offered_variables_are_a_copy(offered):
    variables = {"code": "A"}
    wcl_client._offer("k", REPORT_Q, variables, b"{}")
    variables["code"] = "B"
    assert offered[0].variables == {"code": "A"}


# --- helpers -----------------------------------------------------------------------


def test_operation_name_named_and_anonymous():
    assert operation_name(REPORT_Q) == "ReportQ"
    assert operation_name("  query  MenuDiscovery {\n worldData { zones { id } } }") == "MenuDiscovery"
    assert operation_name("{ rateLimitData { limitPerHour } }") is None


def test_report_codes_variable_form():
    assert report_codes(REPORT_Q, {"code": " aBcD1234 "}) == ["aBcD1234"]


def test_report_codes_literal_form():
    query = '{ reportData { report(code: "LiT9") { title } } }'
    assert report_codes(query, {}) == ["LiT9"]


def test_report_codes_batch_mixed_and_deduplicated():
    query = (
        "query ReportsBatch($c0: String!, $c1: String!, $c2: String!) { reportData {"
        " r0: report(code: $c0) { title } r1: report( code : $c1 ) { title }"
        ' r2: report(code: $c2) { title } r3: report(code: "Z9") { title } } }'
    )
    assert report_codes(query, {"c0": "A1", "c1": "B2", "c2": "A1"}) == ["A1", "B2", "Z9"]


def test_report_codes_skips_unresolved_and_empty_values():
    query = "query Q($a: String, $b: String) { reportData { x: report(code: $a) { t } y: report(code: $b) { t } } }"
    assert report_codes(query, {"b": "  "}) == []


def test_report_codes_none_for_non_report_queries():
    query = "query CharRef($name: String!, $server: String!, $region: String!) { characterData { character(name: $name) { id } } }"
    assert report_codes(query, {"name": "x", "server": "y", "region": "eu"}) == []
