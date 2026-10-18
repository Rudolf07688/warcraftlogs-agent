"""Guides REST API per content type (feature 015, US5 — contracts/guides-api.md)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.api import guides as guides_api
from backend.app.db import repository as repo


@pytest.fixture(autouse=True)
def _live(monkeypatch):
    async def patch_12_1():
        return "12.1"

    async def season_2():
        return "Mythic+ Season 2"

    monkeypatch.setattr(guides_api, "current_patch", patch_12_1)
    monkeypatch.setattr(guides_api, "current_mplus_season", season_2)


async def _publish(s, content_type="raid", **over):
    fields = dict(
        class_name="Mage", spec="Fire", content_type=content_type,
        markdown="# Fire\n- Use Combustion. <!-- c1 -->\n",
        brief={"unconfirmed": ["AoE priority"]}, claims=[{"id": "c1"}], game_patch="12.1",
        season="Mythic+ Season 2" if content_type == "mplus" else None,
        generated_at=datetime(2026, 10, 18, tzinfo=UTC),
        sources=[{"title": "Hotfixes", "uri": "https://worldofwarcraft.blizzard.com/x", "tier": 1,
                  "date": "2026-10-16"}],
        major_cooldowns=[], briefing=None, evidence=None,
    )
    fields.update(over)
    await repo.publish_spec_guide(s, **fields)


async def test_list_is_one_row_per_spec_with_both_types(as_user, session_factory):
    async with session_factory() as s:
        await _publish(s, "mplus")
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="pending")
        await s.commit()
    body = (await as_user.client.get("/api/guides")).json()
    fire = [g for g in body["guides"] if (g["class_name"], g["spec"]) == ("Mage", "Fire")]
    assert len(fire) == 1
    row = fire[0]
    assert row["role"] == "dps" and row["spec_display"] == "Fire"
    assert row["raid"]["status"] == "pending" and row["raid"]["has_published"] is False
    assert row["raid"]["refreshing"] is False and row["raid"]["freshness"] is None
    m = row["mplus"]
    assert m["status"] == "ready" and m["has_published"] is True and m["refreshing"] is False
    assert m["season"] == "Mythic+ Season 2" and m["freshness"] == "current"
    assert body["roster_source"] in {"game_data", "fallback"}
    assert any(g["spec"] == "Devourer" for g in body["guides"])


async def test_refreshing_and_stale_summary(as_user, session_factory):
    async with session_factory() as s:
        await _publish(s)
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="pending", stale_reason="hotfix")
        await s.commit()
    body = (await as_user.client.get("/api/guides")).json()
    raid = next(g for g in body["guides"] if (g["class_name"], g["spec"]) == ("Mage", "Fire"))["raid"]
    assert raid["refreshing"] is True and raid["freshness"] == "possibly_stale"
    assert raid["stale_reason"] == "hotfix"


async def test_detail_published(as_user, session_factory):
    async with session_factory() as s:
        await _publish(s)
        await s.commit()
    body = (await as_user.client.get("/api/guides/Mage/Fire/raid")).json()
    assert body["display"] == "published" and body["content_type"] == "raid"
    assert body["guide_markdown"] == "# Fire\n- Use Combustion.\n"  # claim markers stripped
    assert body["unconfirmed"] == ["AoE priority"] and body["review_issues"] == []
    assert body["sources"] == [{"title": "Hotfixes", "uri": "https://worldofwarcraft.blizzard.com/x",
                                "tier": 1, "date": "2026-10-16"}]


async def test_detail_held_update_keeps_published(as_user, session_factory):
    async with session_factory() as s:
        await _publish(s)
        await repo.hold_spec_guide(
            s, class_name="Mage", spec="Fire", content_type="raid",
            draft={"markdown": "# draft"}, review_issues=[{"kind": "unconfirmed", "detail": "x"}],
        )
        await s.commit()
    body = (await as_user.client.get("/api/guides/Mage/Fire/raid")).json()
    assert body["status"] == "needs_review" and body["display"] == "published"
    assert body["guide_markdown"].startswith("# Fire") and body["review_issues"] == []


async def test_detail_draft_without_published(as_user, session_factory):
    async with session_factory() as s:
        await repo.hold_spec_guide(
            s, class_name="Mage", spec="Fire", content_type="mplus",
            draft={"markdown": "# draft <!-- c1 -->", "brief": {"unconfirmed": ["talents"]}},
            review_issues=[{"claim_id": "c2", "kind": "contradicted", "detail": "Combustion is 120 s, not 90 s"}],
        )
        await s.commit()
    body = (await as_user.client.get("/api/guides/Mage/Fire/mplus")).json()
    assert body["display"] == "draft" and body["guide_markdown"] == "# draft"
    assert body["review_issues"] == ["Combustion is 120 s, not 90 s"]
    assert body["unconfirmed"] == ["talents"]


async def test_detail_none_failed_and_validation(as_user, session_factory):
    none = (await as_user.client.get("/api/guides/Mage/Fire/mplus")).json()
    assert none["display"] == "none" and none["status"] == "none" and none["guide_markdown"] is None
    async with session_factory() as s:
        await repo.fail_spec_guide(s, class_name="Mage", spec="Frost", content_type="raid", reason="patch_unknown")
        await s.commit()
    failed = (await as_user.client.get("/api/guides/Mage/Frost/raid")).json()
    assert failed["status"] == "failed" and failed["failure_reason"] == "patch_unknown"
    assert (await as_user.client.get("/api/guides/Mage/Fire/pvp")).status_code == 422
    assert (await as_user.client.get("/api/guides/Bogus/Spec/raid")).status_code == 404
    assert (await as_user.client.get("/api/guides/Mage/Fire")).status_code == 404  # old path removed


async def test_generate_spawns_only_that_content_type(as_user, monkeypatch):
    seen = []

    async def fake_ensure(class_name, spec, content_type="raid", *, force=False):
        seen.append((class_name, spec, content_type, force))

    monkeypatch.setattr(guides_api, "ensure_guide", fake_ensure)
    r = await as_user.client.post("/api/guides/DemonHunter/Devourer/mplus/generate", json={"force": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending" and r.json()["content_type"] == "mplus"
    assert seen == [("DemonHunter", "Devourer", "mplus", True)]
    assert (await as_user.client.post("/api/guides/Mage/Fire/pvp/generate", json={})).status_code == 422
    assert (await as_user.client.post("/api/guides/Bogus/Spec/raid/generate", json={})).status_code == 404


async def test_generate_rate_limited(as_user, monkeypatch):
    monkeypatch.setattr(guides_api.guide_limiter, "allow_request", lambda key: False)
    r = await as_user.client.post("/api/guides/Mage/Fire/raid/generate", json={})
    assert r.status_code == 429 and r.headers.get("Retry-After")
    assert r.json()["error"]["code"] == "rate_limited"
