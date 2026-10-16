"""Recent-raids storage: the refresh claim, dedupe and character links (feature 013)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from backend.app.db import repository as repo
from backend.app.db.models import RecentRaid, RecentRaidCharacter, RecentRaidRefresh
from backend.app.services.recent_raid_types import ListedReport, ReportDetails

NOW = datetime.now(timezone.utc)


def claim(session, tenant_id, *, cs="set-a", force=False):
    return repo.claim_refresh(
        session, tenant_id=tenant_id, character_set=cs, force=force, min_gap_s=900, stale_s=300
    )


def listed(code: str, *char_ids: uuid.UUID, is_raid: bool = True, hours_ago: float = 30):
    started = NOW - timedelta(hours=hours_ago)
    return ListedReport(
        code=code,
        title=f"Raid {code}",
        zone_id=42,
        zone_name="Nerub-ar Palace",
        guild_name="Guild",
        started_at=started,
        ended_at=started + timedelta(hours=3),
        character_ids=frozenset(char_ids),
        is_raid=is_raid,
    )


async def own(session, tenant_id, name: str):
    return await repo.add_character(
        session, tenant_id=tenant_id, role="self", name=name, server="Ravencrest", region="EU"
    )


# --- claim_refresh / finish_refresh ---------------------------------------------------


async def test_first_claim_wins_and_a_second_within_the_gap_is_refused(session, tenant_id):
    run_id = await claim(session, tenant_id)
    assert run_id is not None
    assert await claim(session, tenant_id) is None  # running
    await repo.finish_refresh(session, tenant_id=tenant_id, run_id=run_id, ok=True, error=None)
    assert await claim(session, tenant_id) is None  # finished just now: gate closed
    row = await repo.get_refresh(session, tenant_id=tenant_id)
    assert row.status == "succeeded" and row.last_success_at is not None


async def test_force_only_wins_after_a_failure(session, tenant_id):
    run_id = await claim(session, tenant_id)
    await repo.finish_refresh(session, tenant_id=tenant_id, run_id=run_id, ok=True, error=None)
    assert await claim(session, tenant_id, force=True) is None  # succeeded: force ignored
    session.expire_all()
    await session.execute(
        update(RecentRaidRefresh)
        .where(RecentRaidRefresh.tenant_id == tenant_id)
        .values(finished_at=NOW - timedelta(hours=1))
    )
    run2 = await claim(session, tenant_id)
    await repo.finish_refresh(session, tenant_id=tenant_id, run_id=run2, ok=False, error="timeout")
    assert await claim(session, tenant_id) is None
    assert await claim(session, tenant_id, force=True) is not None
    session.expire_all()
    row = await repo.get_refresh(session, tenant_id=tenant_id)
    assert row.status == "running" and row.last_error == "timeout"


async def test_a_changed_character_set_opens_the_gate(session, tenant_id):
    run_id = await claim(session, tenant_id, cs="one")
    await repo.finish_refresh(session, tenant_id=tenant_id, run_id=run_id, ok=True, error=None)
    assert await claim(session, tenant_id, cs="one") is None
    assert await claim(session, tenant_id, cs="two") is not None


async def test_a_stale_running_claim_can_be_reclaimed_and_the_old_run_cannot_finish(
    session, tenant_id
):
    old = await claim(session, tenant_id)
    assert await claim(session, tenant_id) is None
    await session.execute(
        update(RecentRaidRefresh)
        .where(RecentRaidRefresh.tenant_id == tenant_id)
        .values(started_at=NOW - timedelta(minutes=6))
    )
    new = await claim(session, tenant_id)
    assert new is not None and new != old  # FR-026
    await repo.finish_refresh(session, tenant_id=tenant_id, run_id=old, ok=False, error="unknown")
    session.expire_all()
    row = await repo.get_refresh(session, tenant_id=tenant_id)
    assert row.status == "running" and row.run_id == new and row.last_error is None


async def test_concurrent_claims_from_two_sessions_yield_exactly_one_winner(
    session_factory, tenant_id
):
    async def attempt():
        async with session_factory() as s:
            run_id = await claim(s, tenant_id)
            await s.commit()
            return run_id

    results = await asyncio.gather(attempt(), attempt())
    assert sum(r is not None for r in results) == 1  # SC-010


async def test_claims_are_per_tenant(session, tenant_id, other_tenant_id):
    assert await claim(session, tenant_id) is not None
    assert await claim(session, other_tenant_id) is not None


# --- upsert_listed_reports / list_recent_raids ----------------------------------------


async def test_one_report_from_two_characters_is_one_row_with_two_links(session, tenant_id):
    a = await own(session, tenant_id, "Alpha")
    b = await own(session, tenant_id, "Beta")
    need = await repo.upsert_listed_reports(
        session, tenant_id=tenant_id, reports=[listed("ABC", a.id)]
    )
    assert need == ["ABC"]
    await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=[listed("ABC", b.id)])
    rows = (await session.execute(select(func.count()).select_from(RecentRaid))).scalar_one()
    links = (
        await session.execute(select(func.count()).select_from(RecentRaidCharacter))
    ).scalar_one()
    assert rows == 1 and links == 2  # SC-005
    [(raid, chars)] = await repo.list_recent_raids(session, tenant_id=tenant_id, limit=20)
    assert raid.report_code == "ABC" and [c.name for c in chars] == ["Alpha", "Beta"]
    assert raid.bosses_pulled is None  # no details yet


async def test_final_reports_are_not_returned_for_details_again(session, tenant_id):
    a = await own(session, tenant_id, "Alpha")
    report = listed("FIN", a.id)
    await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=[report])
    await repo.set_report_details(
        session,
        tenant_id=tenant_id,
        code="FIN",
        details=ReportDetails(report.ended_at, 5, 8, 6, True),
        final_before=NOW - timedelta(hours=2),
    )
    assert await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=[report]) == []
    live = listed("LIVE", a.id, hours_ago=1)
    await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=[live])
    await repo.set_report_details(
        session,
        tenant_id=tenant_id,
        code="LIVE",
        details=ReportDetails(live.ended_at, 4, 3, 1, True),
        final_before=NOW - timedelta(hours=2),
    )
    assert await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=[live]) == [
        "LIVE"
    ]


async def test_list_is_newest_first_raids_only_and_limited(session, tenant_id):
    a = await own(session, tenant_id, "Alpha")
    await repo.upsert_listed_reports(
        session,
        tenant_id=tenant_id,
        reports=[
            listed("OLD", a.id, hours_ago=72),
            listed("NEW", a.id, hours_ago=5),
            listed("MPLUS", a.id, hours_ago=1, is_raid=False),
        ],
    )
    got = await repo.list_recent_raids(session, tenant_id=tenant_id, limit=20)
    assert [r.report_code for r, _ in got] == ["NEW", "OLD"]
    got = await repo.list_recent_raids(session, tenant_id=tenant_id, limit=1)
    assert [r.report_code for r, _ in got] == ["NEW"]


async def test_removing_a_character_hides_raids_only_it_attended(session, tenant_id):
    a = await own(session, tenant_id, "Alpha")
    b = await own(session, tenant_id, "Beta")
    await repo.upsert_listed_reports(
        session,
        tenant_id=tenant_id,
        reports=[listed("ONLY_A", a.id), listed("BOTH", a.id, b.id, hours_ago=10)],
    )
    await repo.delete_character(session, a.id, tenant_id=tenant_id, role="self")
    got = await repo.list_recent_raids(session, tenant_id=tenant_id, limit=20)
    assert [(r.report_code, [c.name for c in cs]) for r, cs in got] == [("BOTH", ["Beta"])]


async def test_other_tenants_raids_are_invisible(session, tenant_id, other_tenant_id):
    a = await own(session, tenant_id, "Alpha")
    await repo.upsert_listed_reports(session, tenant_id=tenant_id, reports=[listed("T1", a.id)])
    assert await repo.list_recent_raids(session, tenant_id=other_tenant_id, limit=20) == []
    assert await repo.get_recent_raid(session, "T1", tenant_id=other_tenant_id) is None
    assert await repo.get_recent_raid(session, "T1", tenant_id=tenant_id) is not None


async def test_links_skip_characters_that_no_longer_exist(session, tenant_id):
    a = await own(session, tenant_id, "Alpha")
    gone = uuid.uuid4()
    await repo.upsert_listed_reports(
        session, tenant_id=tenant_id, reports=[listed("X", a.id, gone)]
    )
    links = (await session.execute(select(RecentRaidCharacter.character_id))).scalars().all()
    assert links == [a.id]
