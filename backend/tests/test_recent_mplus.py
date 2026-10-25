"""Welcome-page recent Mythic+ runs: extraction, refresh, caps and the kickoff (feature 022)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from backend.app.api.recent_raids import mplus_kickoff_prompt_for
from backend.app.config import settings
from backend.app.db import repository as repo
from backend.app.db.models import Conversation, RecentMplusRun
from backend.app.services import recent_raids as svc
from backend.app.services.recent_raid_types import MplusRun
from backend.tests.test_recent_raids import (  # noqa: F401 - fixtures are re-exported
    MPLUS_ZONE,
    FakeWCL,
    _queue_spawns,
    add_own,
    drain,
    fake_wcl,
    report,
)
from wcl_agent.cache.cache_models import FightSummary, ReportSummary
from wcl_agent.client import wcl_client

DUNGEON = "Tazavesh: Streets of Wonder"


def key(fid: int, *, level: int = 12, bonus: int = 1, kill: bool | None = True,
        start: int = 0, name: str = DUNGEON) -> dict[str, Any]:
    return {
        "id": fid, "name": name, "encounterID": 0, "kill": kill, "difficulty": 10,
        "startTime": start, "keystoneLevel": level, "keystoneBonus": bonus,
        "keystoneTime": 1_700_000,
    }


class MplusWCL(FakeWCL):
    """FakeWCL whose report summaries carry keystone fights per report code.

    ``fail_codes`` fails (or ``hang_codes`` stalls) any summary request for those codes;
    ``summary_lanes`` records the WCL lane of every summary request.
    """

    def __init__(self, reports_by_name, fights_by_code):
        super().__init__(reports_by_name)
        self.fights_by_code = fights_by_code
        self.fail_codes: dict[str, BaseException] = {}
        self.hang_codes: set[str] = set()
        self.summary_lanes: list[str] = []

    async def query(self, query, variables=None):
        if "reportData" in query and "fights" in query:
            codes = set((variables or {}).values())
            self.summary_lanes.append(wcl_client._lane.get())
            for code in codes & set(self.fail_codes):
                raise self.fail_codes[code]
            if codes & self.hang_codes:
                await asyncio.Event().wait()
        out = await super().query(query, variables)
        if "reportData" in query and "fights" in query:
            variables = variables or {}
            for i in range(len(variables)):
                node = out["data"]["reportData"].get(f"r{i}")
                if node is not None:
                    node["fights"] = self.fights_by_code.get(variables[f"c{i}"], node["fights"])
        return out


@pytest.fixture
def mplus_wcl(monkeypatch):
    fake = MplusWCL({}, {})
    monkeypatch.setattr(svc, "get_async_client", lambda: fake)
    monkeypatch.setattr("wcl_agent.client.wcl_client.get_async_client", lambda: fake)
    return fake


async def refresh(client):
    await client.get("/api/recent-raids")
    await drain()
    return (await client.get("/api/recent-raids")).json()


def mplus_report(code: str, hours_ago: float) -> dict[str, Any]:
    return report(code, zone=MPLUS_ZONE, ended_hours_ago=hours_ago)


# --- extraction (FR-013, FR-014) -------------------------------------------------------


def summary(*fights: FightSummary) -> ReportSummary:
    return ReportSummary(
        code="R1", start_time_ms=1_000_000, end_time_ms=9_000_000, zone_name="Zone", fights=list(fights)
    )


def test_extract_keeps_completed_keys_and_drops_abandoned():
    cid = frozenset({uuid.uuid4()})
    runs = svc.extract_mplus_runs(
        summary(
            FightSummary(id=1, name="Dungeon A", kill=True, keystone_level=10, keystone_bonus=2, start_time_ms=0),
            FightSummary(id=2, name="Dungeon B", kill=True, keystone_level=11, keystone_bonus=0, start_time_ms=500),
            FightSummary(id=3, name="Dungeon C", kill=False, keystone_level=12, keystone_bonus=0),  # abandoned
            FightSummary(id=4, name="Boss", kill=True),  # not a keystone fight
            FightSummary(id=5, name="", kill=True, keystone_level=9, keystone_bonus=1),
        ),
        cid,
    )
    assert [(r.fight_id, r.dungeon, r.key_level, r.timed) for r in runs] == [
        (1, "Dungeon A", 10, True),
        (2, "Dungeon B", 11, False),  # depleted: listed, not timed
        (5, "Zone", 9, True),  # missing fight name falls back to the zone
    ]
    assert runs[1].started_at == datetime.fromtimestamp(1_000.5, tz=timezone.utc)
    assert runs[0].character_ids == cid


# --- the list: caps, order, no section (FR-002, FR-005) --------------------------------


async def test_six_newest_runs_newest_first_and_raids_capped(as_user, patched_db, mplus_wcl, monkeypatch):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    reports = [mplus_report(f"M{i}", hours_ago=10 + i * 3) for i in range(8)]
    reports += [report(f"RAID{i}", ended_hours_ago=40 + i * 3) for i in range(8)]
    mplus_wcl.reports_by_name = {"Alpha": reports}
    mplus_wcl.fights_by_code = {f"M{i}": [key(1, level=10 + i)] for i in range(8)}
    monkeypatch.setattr(svc, "MPLUS_REPORT_BATCH", 10)

    body = await refresh(as_user.client)
    assert body["refresh"]["status"] == "succeeded"
    levels = [r["key_level"] for r in body["mplus_runs"]]
    assert levels == [10, 11, 12, 13, 14, 15]  # M0 is newest; only 6 shown
    assert len(body["raids"]) == settings.recent_raids_shown == 6
    assert [r["report_code"] for r in body["raids"]] == [f"RAID{i}" for i in range(6)]
    first = body["mplus_runs"][0]
    assert first["dungeon"] == DUNGEON and first["timed"] is True
    assert first["characters"] == [{"name": "Alpha", "server": "Twilight's Hammer", "region": "eu"}]


async def test_no_mplus_runs_means_an_empty_list(as_user, patched_db, mplus_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [report("RAID1")]}
    body = await refresh(as_user.client)
    assert body["mplus_runs"] == [] and [r["report_code"] for r in body["raids"]] == ["RAID1"]
    assert body["refresh"]["status"] == "succeeded"


async def test_several_keys_in_one_report_are_each_a_run(as_user, patched_db, mplus_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [mplus_report("EVENING", 5)]}
    mplus_wcl.fights_by_code = {
        "EVENING": [key(1, level=8, start=0), key(2, level=9, start=3_600_000, bonus=0), key(3, kill=False)]
    }
    body = await refresh(as_user.client)
    assert [(r["fight_id"], r["key_level"], r["timed"]) for r in body["mplus_runs"]] == [
        (2, 9, False),  # newest first
        (1, 8, True),
    ]


async def test_a_run_shared_by_two_characters_is_listed_once(as_user, patched_db, mplus_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha", "Beta")
    shared = mplus_report("SHARED", 5)
    mplus_wcl.reports_by_name = {"Alpha": [shared], "Beta": [shared]}
    mplus_wcl.fights_by_code = {"SHARED": [key(1)]}
    body = await refresh(as_user.client)
    [run] = body["mplus_runs"]
    assert sorted(c["name"] for c in run["characters"]) == ["Alpha", "Beta"]


async def test_a_removed_character_takes_its_runs_off_the_list(as_user, patched_db, mplus_wcl):
    [alpha] = await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [mplus_report("MINE", 5)]}
    mplus_wcl.fights_by_code = {"MINE": [key(1)]}
    assert len((await refresh(as_user.client))["mplus_runs"]) == 1
    async with patched_db() as s:
        await repo.delete_character(s, alpha.id, tenant_id=as_user.tenant_id, role="self")
        await s.commit()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["mplus_runs"] == []


async def test_stored_runs_show_without_waiting_for_wcl(as_user, patched_db, mplus_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [mplus_report("STORED", 5)]}
    mplus_wcl.fights_by_code = {"STORED": [key(1)]}
    await refresh(as_user.client)
    mplus_wcl.calls.clear()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert len(body["mplus_runs"]) == 1 and mplus_wcl.calls == []


async def test_a_raidless_player_sees_stored_runs_while_refreshing_and_after_a_failure(
    as_user, patched_db, mplus_wcl
):
    from backend.tests.test_recent_raids import reopen_gate

    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [mplus_report("KEEP", 5)]}
    mplus_wcl.fights_by_code = {"KEEP": [key(1)]}
    await refresh(as_user.client)
    await reopen_gate(patched_db, as_user.tenant_id)
    mplus_wcl.fail = httpx.ConnectError("down")

    running = (await as_user.client.get("/api/recent-raids")).json()  # starts a refresh
    assert running["refresh"]["status"] == "running"
    assert running["raids"] == [] and len(running["mplus_runs"]) == 1

    await drain()
    body = (await as_user.client.get("/api/recent-raids")).json()
    assert body["refresh"]["status"] == "failed"
    assert body["raids"] == [] and len(body["mplus_runs"]) == 1


def rate_limited() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://www.warcraftlogs.com/api/v2/client")
    return httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))


async def test_an_mplus_step_failure_keeps_the_refresh_raids_and_runs(as_user, patched_db, mplus_wcl):
    from backend.tests.test_recent_raids import reopen_gate

    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [report("RAID1"), mplus_report("OLD", 30)]}
    mplus_wcl.fights_by_code = {"OLD": [key(1, level=10)], "NEW": [key(1, level=15)]}
    await refresh(as_user.client)
    await reopen_gate(patched_db, as_user.tenant_id)

    # The next refresh lists a new raid and a new M+ report; only the M+ summaries hit a 429.
    mplus_wcl.reports_by_name["Alpha"] += [report("RAID2", ended_hours_ago=10), mplus_report("NEW", 5)]
    mplus_wcl.fail_codes = {"NEW": rate_limited()}
    body = await refresh(as_user.client)
    assert body["refresh"]["status"] == "succeeded" and body["refresh"]["last_error"] is None
    assert [r["report_code"] for r in body["raids"]] == ["RAID2", "RAID1"]
    assert [r["key_level"] for r in body["mplus_runs"]] == [10]
    raid2 = next(r for r in body["raids"] if r["report_code"] == "RAID2")
    assert raid2["bosses_pulled"] == 2  # the raid step's details were stored

    # NEW was not marked final, so the next refresh examines it again.
    await reopen_gate(patched_db, as_user.tenant_id)
    mplus_wcl.fail_codes = {}
    body = await refresh(as_user.client)
    assert [r["key_level"] for r in body["mplus_runs"]] == [15, 10]
    assert set(mplus_wcl.summary_lanes) == {"background"}


async def test_an_mplus_step_timeout_does_not_fail_the_refresh(as_user, patched_db, mplus_wcl, monkeypatch):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [report("RAID1"), mplus_report("SLOW", 5)]}
    mplus_wcl.hang_codes = {"SLOW"}
    monkeypatch.setattr(settings, "recent_raids_refresh_timeout_s", 0.5)
    body = await refresh(as_user.client)
    assert body["refresh"]["status"] == "succeeded"
    assert [r["report_code"] for r in body["raids"]] == ["RAID1"] and body["mplus_runs"] == []


async def test_a_finished_nonraid_report_is_not_examined_again(as_user, patched_db, mplus_wcl):
    from backend.tests.test_recent_raids import reopen_gate

    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [mplus_report("OLD", 20)]}
    mplus_wcl.fights_by_code = {"OLD": [key(1)]}
    await refresh(as_user.client)
    before = mplus_wcl.count("reportData")
    await reopen_gate(patched_db, as_user.tenant_id)
    await refresh(as_user.client)
    assert mplus_wcl.count("reportData") == before


async def test_runs_are_private_to_the_tenant(as_user, make_authed_client, patched_db, mplus_wcl):
    other = await make_authed_client("other@example.com")
    try:
        await add_own(patched_db, as_user.tenant_id, "Alpha")
        mplus_wcl.reports_by_name = {"Alpha": [mplus_report("PRIV", 5)]}
        mplus_wcl.fights_by_code = {"PRIV": [key(1)]}
        await refresh(as_user.client)
        await add_own(patched_db, other.tenant_id, "Alpha")
        body = (await other.client.get("/api/recent-raids")).json()
        assert body["mplus_runs"] == []
        resp = await other.client.post("/api/recent-raids/mplus/PRIV/1/investigate", json={})
        assert resp.status_code == 404
    finally:
        await other.client.aclose()


# --- kickoff and title (FR-006, FR-015, FR-016) ----------------------------------------


def test_kickoff_prompt_pins_its_key_phrases():
    prompt = mplus_kickoff_prompt_for("ABC", 7, DUNGEON, 12)
    for phrase in (
        "report ABC", "fight 7", f"{DUNGEON} +12", "against the timer", "timed or depleted",
        "biggest time loss", "who died, to what", "whether it was avoidable",
        "interrupt coverage", "one headline improvement",
        "run and segment level", "cast-level detail only where a segment clearly warrants it",
    ):
        assert phrase in prompt, phrase


async def test_clicking_a_run_creates_an_explicitly_titled_chat(as_user, patched_db, session_factory, mplus_wcl):
    await add_own(patched_db, as_user.tenant_id, "Alpha")
    mplus_wcl.reports_by_name = {"Alpha": [mplus_report("GO", 5)]}
    mplus_wcl.fights_by_code = {"GO": [key(3, level=14)]}
    await refresh(as_user.client)

    resp = await as_user.client.post("/api/recent-raids/mplus/GO/3/investigate", json={})
    assert resp.status_code == 201, resp.text
    assert resp.json()["kickoff_prompt"] == mplus_kickoff_prompt_for("GO", 3, DUNGEON, 14)
    async with session_factory() as s:
        conv = (await s.execute(select(Conversation).where(Conversation.id == uuid.UUID(resp.json()["conversation_id"])))).scalar_one()
    assert conv.title == f"M+ {DUNGEON} +14" and conv.title_source == "explicit"

    assert (await as_user.client.post("/api/recent-raids/mplus/GO/99/investigate", json={})).status_code == 404
    bad = await as_user.client.post("/api/recent-raids/mplus/GO/3/investigate", json={"model": "nope"})
    assert bad.status_code == 400


def test_display_caps_are_separate_from_the_listing_depth():
    assert settings.recent_raids_shown == 6 and settings.recent_mplus_shown == 6
    assert settings.recent_raids_limit == 20


def test_migration_0014_upgrades_and_downgrades():
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0014_recent_mplus_runs.py"
    spec = importlib.util.spec_from_file_location("migration_0014", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == "0013_raw_fetches"

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE tenants (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE user_characters (id VARCHAR(36) PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(conn)):
            mig.upgrade()
            assert {"recent_mplus_runs", "recent_mplus_run_characters"} <= set(
                sa.inspect(conn).get_table_names()
            )
            mig.downgrade()
        assert "recent_mplus_runs" not in sa.inspect(conn).get_table_names()
