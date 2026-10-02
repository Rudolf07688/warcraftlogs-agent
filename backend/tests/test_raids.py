"""US1 tests: tracked-raid upsert/dedup/ordering, capture service, investigate API."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.db import repository as repo
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.services import raids as raids_service


def _naive(dt):
    # SQLite returns naive datetimes for server defaults while Python-set values
    # are tz-aware; normalize for comparison (Postgres returns both tz-aware).
    return dt.replace(tzinfo=None)


async def test_upsert_dedups_by_report_code_and_touches_recency(session):
    r1 = await repo.upsert_tracked_raid(session, report_code="AAAA", label="AAAA")
    first_seen = r1.first_seen_at
    first_asked = r1.last_asked_at

    # Re-reference the same report — no new row, last_asked_at moves forward.
    await asyncio.sleep(0.01)
    r2 = await repo.upsert_tracked_raid(session, report_code="AAAA", label="AAAA")

    raids = await repo.list_tracked_raids(session)
    assert len(raids) == 1
    assert r2.id == r1.id
    assert r2.first_seen_at == first_seen
    assert _naive(r2.last_asked_at) >= _naive(first_asked)


async def test_list_ordered_by_last_asked_desc(session):
    await repo.upsert_tracked_raid(session, report_code="AAAA", label="A raid")
    await asyncio.sleep(0.01)
    await repo.upsert_tracked_raid(session, report_code="BBBB", label="B raid")
    await asyncio.sleep(0.01)
    # Touch A again so it becomes most-recent.
    await repo.upsert_tracked_raid(session, report_code="AAAA", label="A raid")

    raids = await repo.list_tracked_raids(session)
    assert [r.report_code for r in raids] == ["AAAA", "BBBB"]


def test_build_label_formats_guild_zone_date():
    meta = {
        "status": "success",
        "guild": "My Guild",
        "zone": "Liberation of Undermine",
        "start_time_ms": 1_759_000_000_000,
    }
    label, zone, guild, started = raids_service._build_label("CODE", meta)
    assert label.startswith("My Guild — Liberation of Undermine — ")
    assert zone == "Liberation of Undermine"
    assert guild == "My Guild"
    assert started is not None


def test_build_label_falls_back_to_code_when_unresolved():
    label, zone, guild, started = raids_service._build_label("CODE", {"status": "error"})
    assert label == "CODE"
    assert (zone, guild, started) == (None, None, None)


async def test_capture_ignores_non_report_tools_and_failures(session):
    assert await raids_service.capture_raid_from_tool(
        session, name="get_report_table", ok=False, args={"report_code": "X"}, conversation_id=None
    ) is None
    assert await raids_service.capture_raid_from_tool(
        session, name="find_encounter", ok=True, args={}, conversation_id=None
    ) is None
    assert (await repo.list_tracked_raids(session)) == []


async def test_capture_new_raid_resolves_label(monkeypatch, session):
    def fake_meta(code):
        return {"status": "success", "guild": "G", "zone": "Z", "start_time_ms": 1_759_000_000_000}

    monkeypatch.setattr(raids_service, "get_report_metadata", fake_meta)
    raid = await raids_service.capture_raid_from_tool(
        session, name="get_report_graph", ok=True, args={"report_code": "ZZZZ"}, conversation_id=None
    )
    assert raid is not None
    assert raid.report_code == "ZZZZ"
    assert raid.label.startswith("G — Z — ")


def _client_with(session_factory) -> AsyncClient:
    async def override_get_session():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_investigate_creates_empty_conversation_without_persisting(session_factory):
    # Seed a raid directly.
    async with session_factory() as s:
        await repo.upsert_tracked_raid(s, report_code="RRRR", label="R raid")
        await s.commit()

    client = _client_with(session_factory)
    try:
        resp = await client.post("/api/raids/RRRR/investigate", json={})
        assert resp.status_code == 201
        body = resp.json()
        assert "RRRR" in body["kickoff_prompt"]
        assert body["model"]
        conv_id = body["conversation_id"]

        # The conversation exists but has NO messages (kickoff is not persisted).
        detail = await client.get(f"/api/conversations/{conv_id}")
        assert detail.status_code == 200
        assert detail.json()["messages"] == []
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_investigate_unknown_report_is_404(session_factory):
    client = _client_with(session_factory)
    try:
        resp = await client.post("/api/raids/NOPE/investigate", json={})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_investigate_invalid_model_is_400(session_factory):
    async with session_factory() as s:
        await repo.upsert_tracked_raid(s, report_code="RRRR", label="R raid")
        await s.commit()

    client = _client_with(session_factory)
    try:
        resp = await client.post("/api/raids/RRRR/investigate", json={"model": "bogus-model"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


# --- US2: encounters merge + race-safe upsert ---------------------------------


async def test_upsert_merges_encounters_without_duplicating(session):
    await repo.upsert_tracked_raid(
        session,
        report_code="ENC1",
        label="ENC1",
        encounters=[{"encounter_id": 2902, "name": "Ulgrax", "difficulty": 5, "kill": False}],
    )
    # Re-reference with an overlapping boss (now a kill) plus a new one.
    raid = await repo.upsert_tracked_raid(
        session,
        report_code="ENC1",
        label="ENC1",
        encounters=[
            {"encounter_id": 2902, "name": "Ulgrax", "difficulty": 5, "kill": True},
            {"encounter_id": 2917, "name": "Sikran", "difficulty": 5, "kill": False},
        ],
    )
    raids = await repo.list_tracked_raids(session)
    assert len(raids) == 1  # no duplicate row
    by_id = {e["encounter_id"]: e for e in raid.encounters}
    assert set(by_id) == {2902, 2917}  # deduped by encounter_id
    assert by_id[2902]["kill"] is True  # a later kill upgrades the earlier non-kill


async def test_capture_persists_distinct_encounters_from_fights(monkeypatch, session):
    monkeypatch.setattr(
        raids_service, "get_report_metadata", lambda code: {"status": "error"}
    )
    result = {
        "status": "success",
        "fights": [
            {"id": 1, "name": "Ulgrax", "encounterID": 2902, "difficulty": 5, "kill": False},
            {"id": 2, "name": "Ulgrax", "encounterID": 2902, "difficulty": 5, "kill": True},
            {"id": 3, "name": "Trash", "encounterID": 0, "kill": False},
        ],
    }
    raid = await raids_service.capture_raid_from_tool(
        session,
        name="get_report_fights",
        ok=True,
        args={"report_code": "FGT1"},
        conversation_id=None,
        result=result,
    )
    assert raid is not None
    assert [e["encounter_id"] for e in raid.encounters] == [2902]
    assert raid.encounters[0]["kill"] is True


async def test_concurrent_first_reference_converges_to_one_row(tmp_path):
    # True concurrency needs real connections, so use a file-backed SQLite (the
    # shared in-memory StaticPool can't model two racing transactions). A generous
    # busy timeout lets the losing writer wait, hit the unique violation, and fall
    # through to the update branch instead of erroring.
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from backend.app.db.models import Base

    db_path = tmp_path / "race.db"
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", connect_args={"timeout": 30}
    )
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)

        async def do_upsert(enc):
            async with factory() as s:
                await repo.upsert_tracked_raid(
                    s, report_code="RACE", label="RACE", encounters=enc
                )
                await s.commit()

        await asyncio.gather(
            do_upsert([{"encounter_id": 2902, "name": "Ulgrax", "difficulty": 5, "kill": True}]),
            do_upsert([{"encounter_id": 2917, "name": "Sikran", "difficulty": 5, "kill": False}]),
        )

        async with factory() as s:
            raids = await repo.list_tracked_raids(s)
        assert len(raids) == 1  # concurrent first references converged to one row
    finally:
        await eng.dispose()
