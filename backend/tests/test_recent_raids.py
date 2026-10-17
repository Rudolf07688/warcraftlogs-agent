"""Welcome-page recent raids: the refresh service and the REST API (feature 013)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update

from backend.app.config import settings
from backend.app.db import repository as repo
from backend.app.db.models import RecentRaid, RecentRaidRefresh
from backend.app.services import background
from backend.app.services import recent_raids as svc
from wcl_agent import wcl_client
from wcl_agent.cache import get_cache

RAID_ZONE, MPLUS_ZONE = 53, 99
HOUR_MS = 3_600_000
NOW_MS = int(time.time() * 1000)

ZONES = {
    "data": {
        "worldData": {
            "zones": [
                {"id": RAID_ZONE, "name": "The Venomous Abyss", "difficulties": [{"id": 3}, {"id": 4}, {"id": 5}]},
                {"id": MPLUS_ZONE, "name": "Mythic+ Season 2", "difficulties": [{"id": 10}]},
            ]
        }
    }
}


def report(code: str, *, zone: int = RAID_ZONE, ended_hours_ago: float = 20) -> dict[str, Any]:
    end = NOW_MS - int(ended_hours_ago * HOUR_MS)
    return {
        "code": code,
        "title": f"Title {code}",
        "startTime": end - 3 * HOUR_MS,
        "endTime": end,
        "zone": {"id": zone, "name": "The Venomous Abyss" if zone == RAID_ZONE else "M+"},
        "guild": {"name": "Guild"},
    }


FIGHTS = [
    {"encounterID": 1, "kill": False, "difficulty": 4},
    {"encounterID": 1, "kill": True, "difficulty": 4},
    {"encounterID": 2, "kill": False, "difficulty": 5},
    {"encounterID": 3, "kill": True, "difficulty": 108},  # not a raid difficulty: ignored
]


class FakeWCL:
    """Answers the zone list, the aliased recentReports and the aliased report details."""

    def __init__(self, reports_by_name: dict[str, list[dict[str, Any]]]):
        self.reports_by_name = reports_by_name
        self.calls: list[tuple[str, dict[str, Any], bool]] = []
        self.gate: asyncio.Event | None = None
        self.fail: BaseException | None = None

    def count(self, needle: str) -> int:
        return sum(1 for q, _, _ in self.calls if needle in q)

    async def query(self, query: str, variables: dict | None = None, *, cache: bool = True):
        variables = variables or {}
        self.calls.append((query, variables, cache))
        if self.gate is not None and "recentReports" in query:
            await self.gate.wait()
        if self.fail is not None and "worldData" not in query:
            raise self.fail
        if "worldData" in query:
            return ZONES
        if "recentReports" in query:
            out = {}
            i = 0
            while f"n{i}" in variables:
                items = self.reports_by_name.get(variables[f"n{i}"])
                out[f"c{i}"] = None if items is None else {"recentReports": {"data": items}}
                i += 1
            return {"data": {"characterData": out}}
        if "reportData" in query:
            known = {r["code"]: r for rs in self.reports_by_name.values() for r in rs}
            out = {}
            i = 0
            while f"c{i}" in variables:
                r = known[variables[f"c{i}"]]
                out[f"r{i}"] = {"endTime": r["endTime"], "zone": r["zone"], "fights": FIGHTS}
                i += 1
            return {"data": {"reportData": out}}
        raise AssertionError(f"unexpected query: {query[:60]}")


@pytest.fixture
def fake_wcl(monkeypatch):
    fake = FakeWCL({})
    monkeypatch.setattr(svc, "get_async_client", lambda: fake)
    monkeypatch.setattr(wcl_client, "get_async_client", lambda: fake)  # patch.raid_zone_ids
    get_cache().clear()
    return fake


# Refresh runs are queued and run by drain(), never concurrently with a request: the test
# engine is ONE shared SQLite connection (StaticPool), so a background session committing
# mid-request would interleave with the request's transaction. Production sessions each
# get their own pooled connection.
_queued: list = []


@pytest.fixture(autouse=True)
def _queue_spawns(monkeypatch):
    _queued.clear()
    monkeypatch.setattr(background, "spawn", lambda coro, key: _queued.append(coro))
    yield
    for coro in _queued:
        coro.close()
    _queued.clear()


async def drain() -> None:
    while _queued:
        await _queued.pop(0)


async def add_own(session_factory, tenant_id, *names: str):
    async with session_factory() as s:
        chars = [
            await repo.add_character(
                s, tenant_id=tenant_id, role="self", name=n, server="Twilight's Hammer", region="eu"
            )
            for n in names
        ]
        await s.commit()
        return chars


async def reopen_gate(session_factory, tenant_id) -> None:
    async with session_factory() as s:
        await s.execute(
            update(RecentRaidRefresh)
            .where(RecentRaidRefresh.tenant_id == tenant_id)
            .values(finished_at=None, status="succeeded")
        )
        await s.commit()


# --- US1 ------------------------------------------------------------------------------


async def test_refresh_stores_raids_with_details_and_leaves_out_non_raids(
    as_user, patched_db, fake_wcl
):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.reports_by_name = {
        "Alpha": [report("RAID1"), report("MPLUS1", zone=MPLUS_ZONE, ended_hours_ago=2)]
    }
    first = (await as_user.client.get("/api/recent-raids")).json()
    assert first["has_characters"] is True and first["refresh"]["status"] == "running"
    await drain()

    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["refresh"]["status"] == "succeeded"
    assert [r["report_code"] for r in body["raids"]] == ["RAID1"]
    raid = body["raids"][0]
    assert raid["zone_name"] == "The Venomous Abyss" and raid["difficulty"] == 5
    assert (raid["bosses_pulled"], raid["bosses_killed"]) == (2, 1)
    assert raid["is_final"] is True
    assert raid["characters"] == [{"name": "Alpha", "server": "Twilight's Hammer", "region": "eu"}]

    [list_call] = [c for c in fake_wcl.calls if "recentReports" in c[0]]
    assert list_call[1]["s0"] == "twilights-hammer" and list_call[1]["r0"] == "EU"
    assert list_call[2] is False  # the list step bypasses the cache
    async with patched_db() as s:  # the Mythic+ report is stored, just not listed
        codes = set((await s.execute(select(RecentRaid.report_code))).scalars())
    assert codes == {"RAID1", "MPLUS1"}


async def test_one_report_from_two_characters_is_listed_once_with_both(
    as_user, patched_db, fake_wcl
):
    await add_own(patched_db, as_user.tenant_id, "Alpha", "Beta", "Ghost")
    shared = report("SHARED")
    fake_wcl.reports_by_name = {"Alpha": [shared], "Beta": [shared]}  # Ghost: not on WCL
    await as_user.client.get("/api/recent-raids")
    await drain()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert len(body["raids"]) == 1  # SC-005
    assert sorted(c["name"] for c in body["raids"][0]["characters"]) == ["Alpha", "Beta"]
    assert fake_wcl.count("recentReports") == 1  # one request for every character


async def test_bosses_null_until_details(patched_db, as_user, fake_wcl):
    [alpha] = await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.reports_by_name = {"Alpha": [report("EARLY")]}
    listed = await svc.fetch_listed_reports([alpha], {RAID_ZONE})
    async with patched_db() as s:
        await repo.upsert_listed_reports(s, tenant_id=as_user.tenant_id, reports=listed)
        await s.commit()
    fake_wcl.gate = asyncio.Event()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert [(r["report_code"], r["bosses_pulled"], r["bosses_killed"]) for r in body["raids"]] == [
        ("EARLY", None, None)
    ]
    fake_wcl.gate.set()
    await drain()


async def test_no_characters_means_no_wcl_call(as_user, fake_wcl):
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body == {
        "has_characters": False,
        "raids": [],
        "refresh": {"status": "idle", "last_success_at": None, "last_error": None},
    }
    assert fake_wcl.calls == []


async def test_get_returns_stored_raids_without_waiting_for_wcl(as_user, patched_db, fake_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.reports_by_name = {"Alpha": [report("R1")]}
    await as_user.client.get("/api/recent-raids")
    await drain()
    await reopen_gate(patched_db, as_user.tenant_id)

    fake_wcl.gate = asyncio.Event()  # WCL now hangs until released
    resp = await asyncio.wait_for(as_user.client.get("/api/recent-raids"), 2)  # FR-010
    body = resp.json()
    assert [r["report_code"] for r in body["raids"]] == ["R1"]
    assert body["refresh"]["status"] == "running"
    fake_wcl.gate.set()
    await drain()


async def test_recent_raids_require_a_session(client):
    assert (await client.get("/api/recent-raids")).status_code == 401


async def test_list_step_raises_http_errors_unchanged(monkeypatch, patched_db, as_user):
    [alpha] = await add_own(patched_db, as_user.tenant_id, "Alpha")

    class Boom:
        async def query(self, *a, **k):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(svc, "get_async_client", lambda: Boom())
    with pytest.raises(httpx.ConnectError):
        await svc.fetch_listed_reports([alpha], set())


def test_character_set_hash_ignores_order_and_case():
    class C:
        def __init__(self, name):
            self.name, self.server, self.region = name, "Realm", "EU"

    assert svc.character_set_hash([C("A"), C("b")]) == svc.character_set_hash([C("B"), C("a")])
    assert svc.character_set_hash([C("A")]) != svc.character_set_hash([C("A"), C("B")])
    assert settings.recent_raids_limit == 20


# --- US3: stored raids, the refresh gate, failures and Retry --------------------------


async def test_final_reports_are_never_fetched_again(as_user, patched_db, fake_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.reports_by_name = {"Alpha": [report("OLD1"), report("OLD2", ended_hours_ago=48)]}
    await as_user.client.get("/api/recent-raids")
    await drain()
    assert fake_wcl.count("reportData") == 1

    await reopen_gate(patched_db, as_user.tenant_id)
    fake_wcl.calls.clear()
    get_cache().clear()  # prove the skip comes from storage, not the WCL cache
    await as_user.client.get("/api/recent-raids")
    await drain()
    assert fake_wcl.count("reportData") == 0  # FR-012 / SC-004
    list_calls = [c for c in fake_wcl.calls if "recentReports" in c[0]]
    assert len(list_calls) == 1 and list_calls[0][2] is False


async def test_a_live_report_stays_non_final_and_is_fetched_again(as_user, patched_db, fake_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.reports_by_name = {"Alpha": [report("LIVE", ended_hours_ago=0.5)]}
    await as_user.client.get("/api/recent-raids")
    await drain()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["raids"][0]["is_final"] is False

    await reopen_gate(patched_db, as_user.tenant_id)
    fake_wcl.calls.clear()
    get_cache().clear()
    await as_user.client.get("/api/recent-raids")
    await drain()
    assert fake_wcl.count("reportData") == 1


async def test_wcl_down_records_a_failure_and_keeps_stored_raids(as_user, patched_db, fake_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.reports_by_name = {"Alpha": [report("KEEP")]}
    await as_user.client.get("/api/recent-raids")
    await drain()

    await reopen_gate(patched_db, as_user.tenant_id)
    fake_wcl.fail = httpx.ConnectError("down")
    await as_user.client.get("/api/recent-raids")
    await drain()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["refresh"]["status"] == "failed"
    assert body["refresh"]["last_error"] == "wcl_unavailable"  # FR-015, SC-006
    assert [r["report_code"] for r in body["raids"]] == ["KEEP"]


async def test_rate_limits_are_reported_as_such(as_user, patched_db, fake_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    request = httpx.Request("POST", wcl_client.GRAPHQL_URL)
    fake_wcl.fail = httpx.HTTPStatusError(
        "429", request=request, response=httpx.Response(429, request=request)
    )
    await as_user.client.get("/api/recent-raids")
    await drain()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["refresh"]["last_error"] == "rate_limited"


async def test_a_hanging_refresh_times_out(as_user, patched_db, fake_wcl, monkeypatch):
    monkeypatch.setattr(settings, "recent_raids_refresh_timeout_s", 1)
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.gate = asyncio.Event()  # never released
    await as_user.client.get("/api/recent-raids")
    await asyncio.wait_for(drain(), 5)
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["refresh"]["status"] == "failed" and body["refresh"]["last_error"] == "timeout"


async def test_adding_a_character_starts_a_refresh_within_the_gap(as_user, patched_db, fake_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.reports_by_name = {"Alpha": []}
    await as_user.client.get("/api/recent-raids")
    await drain()
    assert (await as_user.client.get("/api/recent-raids")).json()["refresh"]["status"] == "succeeded"

    await add_own(patched_db, as_user.tenant_id, "Beta")
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["refresh"]["status"] == "running"  # FR-013: the character set changed
    await drain()


async def test_retry_endpoint(as_user, patched_db, fake_wcl):
    assert (await as_user.client.post("/api/recent-raids/refresh")).json() == {
        "detail": "no_characters"
    }
    assert (await as_user.client.post("/api/recent-raids/refresh")).status_code == 409

    await add_own(patched_db, as_user.tenant_id, "Alpha")
    fake_wcl.fail = httpx.ConnectError("down")
    await as_user.client.get("/api/recent-raids")
    await drain()

    fake_wcl.fail = None
    fake_wcl.reports_by_name = {"Alpha": [report("BACK")]}
    fake_wcl.gate = asyncio.Event()
    resp = await as_user.client.post("/api/recent-raids/refresh")
    assert resp.status_code == 202, resp.json()
    assert resp.json()["status"] == "running"

    again = await as_user.client.post("/api/recent-raids/refresh")  # still running
    assert again.status_code == 200 and again.json()["status"] == "running"
    fake_wcl.gate.set()
    await drain()

    done = await as_user.client.post("/api/recent-raids/refresh")  # succeeded: not due
    assert done.status_code == 200 and done.json()["status"] == "succeeded"


async def test_retry_needs_csrf(as_user, patched_db):
    from httpx import ASGITransport, AsyncClient

    from backend.app.main import app

    headers = {k: v for k, v in as_user.client.headers.items() if k != "x-csrf-token"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as c:
        assert (await c.post("/api/recent-raids/refresh")).status_code == 403
