"""Guides per content type: storage identity and the published/latest-run split (feature 015).

The schema comes from ``metadata.create_all`` (as every test here); migration 0011 mirrors it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.db import repository as repo
from backend.app.db.models import SpecGuide


async def _publish(session, content_type="raid", **over):
    fields = dict(
        class_name="Mage",
        spec="Fire",
        content_type=content_type,
        markdown="# Fire",
        brief={"patch": "12.1"},
        claims=[{"id": "c1"}],
        game_patch="12.1",
        season="Mythic+ Season 2" if content_type == "mplus" else None,
        generated_at=datetime(2026, 10, 18, tzinfo=UTC),
        sources=[{"title": "Blizzard", "uri": "https://example.test"}],
        major_cooldowns=[{"name": "Combustion", "cooldown_s": 120}],
        briefing={"live_patch": "12.1"},
        evidence={"fact_sheet": {"items": []}},
    )
    fields.update(over)
    return await repo.publish_spec_guide(session, **fields)


async def test_raid_and_mplus_rows_coexist_for_one_spec(session):
    await repo.upsert_spec_guide(session, class_name="Mage", spec="Fire", status="pending")
    await repo.upsert_spec_guide(
        session, class_name="Mage", spec="Fire", content_type="mplus", status="ready"
    )
    await session.commit()
    raid = await repo.get_spec_guide(session, class_name="Mage", spec="Fire")
    mplus = await repo.get_spec_guide(
        session, class_name="Mage", spec="Fire", content_type="mplus"
    )
    assert raid.status == "pending" and raid.content_type == "raid"
    assert mplus.status == "ready" and mplus.id != raid.id


async def test_identity_is_unique_per_content_type(session):
    session.add(SpecGuide(class_name="Mage", spec="Fire", content_type="raid", status="ready"))
    await session.flush()
    session.add(SpecGuide(class_name="Mage", spec="Fire", content_type="raid", status="ready"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_publish_clears_latest_run_leftovers(session):
    await repo.upsert_spec_guide(
        session,
        class_name="Mage",
        spec="Fire",
        status="failed",
        draft={"x": 1},
        review_issues=[{"kind": "other"}],
        failure_reason="model_error",
        stale_reason="legacy",
    )
    g = await _publish(session)
    assert g.status == "ready" and g.guide_markdown == "# Fire"
    assert g.brief == {"patch": "12.1"} and g.claims == [{"id": "c1"}]
    assert g.draft is None and g.review_issues is None
    assert g.failure_reason is None and g.stale_reason is None


async def test_hold_and_fail_keep_the_published_version(session):
    await _publish(session)
    held = await repo.hold_spec_guide(
        session,
        class_name="Mage",
        spec="Fire",
        content_type="raid",
        draft={"markdown": "# draft"},
        review_issues=[{"kind": "unconfirmed", "detail": "x"}],
    )
    assert held.status == "needs_review" and held.draft == {"markdown": "# draft"}
    assert held.guide_markdown == "# Fire" and held.brief == {"patch": "12.1"}
    assert held.game_patch == "12.1"

    failed = await repo.fail_spec_guide(
        session, class_name="Mage", spec="Fire", content_type="raid", reason="patch_unknown"
    )
    assert failed.status == "failed" and failed.failure_reason == "patch_unknown"
    assert failed.guide_markdown == "# Fire" and failed.brief == {"patch": "12.1"}


async def test_unknown_stamp_column_is_rejected(session):
    with pytest.raises(TypeError):
        await repo.upsert_spec_guide(
            session, class_name="Mage", spec="Fire", status="ready", bogus=1
        )


async def test_batch_reads_key_by_content_type(session):
    await _publish(session)
    await _publish(session, content_type="mplus")
    await repo.upsert_spec_guide(
        session, class_name="Priest", spec="Holy", content_type="mplus", status="pending"
    )
    await session.commit()
    keys = [("Mage", "Fire", "raid"), ("Mage", "Fire", "mplus"), ("Priest", "Holy", "mplus")]
    rows = await repo.get_spec_guides_for(session, keys, with_text=False)
    assert set(rows) == set(keys)
    assert rows[("Mage", "Fire", "mplus")].season == "Mythic+ Season 2"
    assert repo.guide_has_published(rows[("Mage", "Fire", "raid")])
    assert not repo.guide_has_published(rows[("Priest", "Holy", "mplus")])
    ready = await repo.get_spec_guides_for(session, keys, ready_only=True)
    assert set(ready) == {("Mage", "Fire", "raid"), ("Mage", "Fire", "mplus")}
    listed = await repo.list_spec_guides(session, with_text=False)
    assert {(g.content_type, repo.guide_has_published(g)) for g in listed} == {
        ("raid", True),
        ("mplus", True),
        ("mplus", False),
    }
