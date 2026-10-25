"""``get_coaching_brief`` (feature 015, US2 — contracts/agent-context.md §2.2)."""

from __future__ import annotations

import pytest

from wcl_agent.guides.guide_meta import BriefRecord, clear_brief_loader, set_brief_loader
from wcl_agent.guides.guides_tool import get_coaching_brief


@pytest.fixture
def loader():
    asked = []

    async def load(class_name, spec, content_type):
        asked.append((class_name, spec, content_type))
        if (class_name, spec, content_type) == ("DemonHunter", "Devourer", "raid"):
            return BriefRecord(class_name, spec, "raid", "COACHING BRIEF — Devourer", (), "12.1.5",
                               None, None, "current", False)
        return None

    set_brief_loader(load)
    yield asked
    clear_brief_loader()


async def test_success_with_loose_names(loader):
    res = await get_coaching_brief("demon hunter", "devourer", "raid")
    assert res["status"] == "success" and res["brief"] == "COACHING BRIEF — Devourer"
    assert res["content_type"] == "raid" and res["freshness"] == "current"
    assert res["data_sufficient"] is False and "provenance" in res
    assert loader == [("DemonHunter", "Devourer", "raid")]


async def test_missing_content_type_is_no_brief_without_fallback(loader):
    res = await get_coaching_brief("DemonHunter", "Devourer", "mplus")
    assert res["status"] == "no_brief" and "brief" not in res
    assert res["message"] == (
        "No verified Mythic+ guidance for Devourer Demon Hunter. Coach from measured log data "
        "only; do not apply the other content type's brief."
    )
    assert loader == [("DemonHunter", "Devourer", "mplus")]  # the raid brief was never read


async def test_unknown_spec_lists_valid_specs(loader):
    res = await get_coaching_brief("Demon Hunter", "Felbender", "raid")
    assert res["status"] == "error" and res["valid_specs"] == ["Havoc", "Vengeance", "Devourer"]
    res = await get_coaching_brief("Paladruid", "Holy", "raid")
    assert res["status"] == "error" and "Mage" in res["valid_classes"]


async def test_invalid_content_type(loader):
    res = await get_coaching_brief("Mage", "Fire", "pvp")
    assert res["status"] == "error" and res["valid_content_types"] == ["raid", "mplus"]


async def test_no_loader_means_no_brief():
    clear_brief_loader()
    assert (await get_coaching_brief("Mage", "Fire", "raid"))["status"] == "no_brief"


async def test_a_held_draft_never_reaches_the_tool(session_factory, monkeypatch):
    # Through the real backend loader: a needs_review run with no published version.
    from backend.app.db import repository as repo
    from backend.app.db import session as db_session
    from backend.app.services import guide

    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    guide.invalidate_brief_cache()
    async with session_factory() as s:
        await repo.hold_spec_guide(
            s, class_name="Mage", spec="Fire", content_type="raid",
            draft={"brief": {"class_name": "Mage"}, "markdown": "# draft"}, review_issues=[],
        )
        await s.commit()
    set_brief_loader(guide.load_brief_record)
    try:
        assert (await get_coaching_brief("Mage", "Fire", "raid"))["status"] == "no_brief"
    finally:
        clear_brief_loader()
