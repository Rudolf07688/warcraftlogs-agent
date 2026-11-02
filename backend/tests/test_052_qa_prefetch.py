"""QA fix round 2026-11-02 for the kickoff pre-fetch (052; BUG-001, PERF-003, BUG-003).

It warms exactly the fights the kickoff turn asks for (``get_report_fights``'s ``bosses``, no
Mythic+ key runs), as raw tables the turn then reads from the store, without compacting them,
and it doesn't start while the store skips the clicking workspace.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from backend.app.config import settings
from backend.app.services import kickoff_prefetch, raw_fetch_reads
from backend.app.services.kickoff_prefetch import MAX_BOSS_TABLES, pick_boss_fights
from backend.app.services.raw_fetch_reads import TIMEOUTS_TO_OPEN, Breaker
from backend.app.tenancy.context import RequestIdentity, current_identity
from backend.tests.test_050_report_fights import _fight, _night
from backend.tests.wcl_fakes import gql_response, mock_async_client
from wcl_agent.cache.cache_models import ReportSummary
from wcl_agent.client import wcl_client
from wcl_agent.client.wcl_client import FetchedResponse, StoredFetch
from wcl_agent.tools import report_tools

# --- BUG-001: the turn's fights, no key runs ------------------------------------------------------


def test_the_picks_are_the_bosses_the_turn_asks_for():
    summary = _night()
    wanted = [b["last_kill_fight_id"] or b["last_pull_fight_id"] for b in report_tools.boss_summary(summary)]
    assert pick_boss_fights(summary) == wanted == [4, 11, 20, 33, 32, 34]  # no key runs 1, 2, 40


def test_key_runs_never_push_bosses_out_of_the_cap():
    keys = [_fight(i, i * 1_000, 12_000 + i, f"Key {i}", 10, True, keystone=10) for i in range(1, 9)]
    bosses = [_fight(20 + i, 50_000 + i * 1_000, 3_000 + i, f"Boss {i}", kill=True) for i in range(4)]
    summary = ReportSummary(code="Keys1", start_time_ms=0, end_time_ms=1, fights=keys + bosses)
    assert pick_boss_fights(summary) == [20, 21, 22, 23]
    assert len(pick_boss_fights(_many_bosses())) == MAX_BOSS_TABLES


def _many_bosses() -> ReportSummary:
    fights = [_fight(i, i * 1_000, 3_000 + i, f"Boss {i}", kill=True) for i in range(1, 16)]
    return ReportSummary(code="Many1", start_time_ms=0, end_time_ms=1, fights=fights)


# --- PERF-003: raw tables, read back by the turn from the store -----------------------------------


class _DictStore:
    """The fetch sink and source in one: what the network answered, served by query key."""

    def __init__(self) -> None:
        self.rows: dict[str, bytes] = {}

    def sink(self, item) -> None:
        if isinstance(item, FetchedResponse):
            self.rows[item.query_key] = item.content

    def scope(self) -> str:
        identity = current_identity.get()
        return str(identity.tenant_id) if identity and identity.tenant_id else ""

    async def __call__(self, query_key, query, variables):
        content = self.rows.get(query_key)
        return None if content is None else StoredFetch(content, True)


TABLE = {"totalTime": 300_000, "damageDone": [{"name": f"P{i}", "total": 1000 - i} for i in range(30)],
         "playerDetails": {"dps": [{"name": "P1"}]}}


@pytest.fixture
def wcl(monkeypatch):
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        return gql_response({"data": {"reportData": {"report": {"table": TABLE}}}})

    client = mock_async_client(handler)
    store = _DictStore()
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: client)
    monkeypatch.setattr(wcl_client, "_fetch_sink", store.sink)
    monkeypatch.setattr(wcl_client, "_fetch_source", store)
    return calls, store


async def test_the_turn_reads_the_warmed_tables_from_the_store(wcl, monkeypatch, tenant_id):
    calls, store = wcl
    summary = ReportSummary(code="Warm1", start_time_ms=0, end_time_ms=1, fights=[
        _fight(1, 1_000, 3001, "Vexie", kill=True), _fight(2, 2_000, 3002, "Cauldron", kill=False)])

    async def load(_code):
        return summary

    compacted: list[object] = []

    async def never(table):
        compacted.append(table)
        return table

    compact, overview = report_tools.acompact_table, report_tools.aoverview_table
    monkeypatch.setattr(kickoff_prefetch, "load_report_summary", load)
    monkeypatch.setattr(report_tools, "acompact_table", never)
    monkeypatch.setattr(report_tools, "aoverview_table", never)
    identity = RequestIdentity(uuid.uuid4(), tenant_id, "member", False, uuid.uuid4())
    await asyncio.create_task(kickoff_prefetch.prefetch(identity, "Warm1"))
    assert calls["n"] == 2 and len(store.rows) == 2  # one raw table per boss, stored
    assert compacted == []  # nothing compacted or neutralised for tables nobody reads here
    monkeypatch.setattr(report_tools, "acompact_table", compact)  # the turn's tools compact
    monkeypatch.setattr(report_tools, "aoverview_table", overview)
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: mock_async_client(_no_network))
    token = current_identity.set(identity)
    try:
        for fight_id in (1, 2):
            result = await report_tools.get_report_table("Warm1", "Summary", fight_id=fight_id, overview=True)
            assert result["status"] == "success", result
            assert "P0" in json.dumps(result["table"])
    finally:
        current_identity.reset(token)


async def _no_network(request):
    raise AssertionError("the turn went to Warcraft Logs for a warmed table")


# --- BUG-003: no pre-fetch while the store skips the clicking workspace ---------------------------


@pytest.fixture
def store_running(monkeypatch):
    monkeypatch.setattr(kickoff_prefetch, "_started", {})
    monkeypatch.setattr(raw_fetch_reads, "breaker", Breaker())
    monkeypatch.setattr(settings, "wcl_store_reads_enabled", True)
    monkeypatch.setattr(wcl_client, "_fetch_source", object())
    spawned: list = []

    def spawn(coro, key):
        coro.close()
        spawned.append(key)

    monkeypatch.setattr(kickoff_prefetch.background, "spawn", spawn)
    return spawned


def _identity(tenant: uuid.UUID) -> RequestIdentity:
    return RequestIdentity(uuid.uuid4(), tenant, "member", False, uuid.uuid4())


def test_a_workspace_skipping_the_store_gets_no_pre_fetch(store_running, tenant_id, other_tenant_id):
    breaker = raw_fetch_reads.breaker
    for _ in range(TIMEOUTS_TO_OPEN):
        breaker.timed_out(False, tenant_id)
    assert breaker.open_until == 0  # one workspace: the breaker itself stays closed
    assert kickoff_prefetch.schedule(_identity(tenant_id), "Skip1") is False
    assert kickoff_prefetch._started == {}  # no cooldown spent
    assert kickoff_prefetch.schedule(_identity(other_tenant_id), "Skip1") is True


def test_skips_takes_no_trial_and_follows_the_breaker(store_running, tenant_id):
    breaker = raw_fetch_reads.breaker
    assert breaker.skips(tenant_id) is False
    breaker.failed()
    assert breaker.skips(tenant_id) is True
    breaker.open_until = breaker.clock() - 1  # half-open: a caller may try
    assert breaker.skips(tenant_id) is False and not breaker.trial
