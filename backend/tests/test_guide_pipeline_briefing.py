"""Generation briefing: live build, hotfix feed, patch/season rules (feature 015, US1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.services.guide_pipeline import briefing
from backend.app.services.guide_pipeline.briefing import (
    PatchUnknown,
    SeasonUnknown,
    build_briefing,
    hotfix_touch_time,
    newest_hotfix_url,
    parse_hotfix_article,
    parse_versions,
)
from backend.tests.test_guide_meta import MENU_PAYLOAD
from backend.tests.wcl_fakes import install
from wcl_agent.cache.cache_models import HotfixEntry, HotfixFeed, LiveVersion

FIXTURES = Path(__file__).parent / "fixtures"

VERSIONS = """Region!STRING:0|BuildConfig!HEX:16|CDNConfig!HEX:16|KeyRing!HEX:16|BuildId!DEC:4|VersionsName!String:0|ProductConfig!HEX:16
## seqn = 4083218
us|88d5|f065|3ca5|70448|12.1.5.70448|5302
eu|88d5|f065|3ca5|70447|12.1.5.70447|5302
"""


# --- version endpoint -------------------------------------------------------------------


def test_parse_versions_reads_the_us_row():
    v = parse_versions(VERSIONS)
    assert v.version == "12.1.5.70448" and v.build_id == 70448 and v.seqn == 4083218
    assert v.patch == "12.1.5"
    assert parse_versions(VERSIONS, region="eu").build_id == 70447


@pytest.mark.parametrize("body", ["", "garbage", VERSIONS.replace("12.1.5.70448", "not-a-version")])
def test_parse_versions_rejects_bad_input(body):
    assert parse_versions(body) is None


# --- hotfix feed --------------------------------------------------------------------------


def test_newest_hotfix_url_from_listing_json_and_href():
    listing = '{"blogList":{"blogs":[{"title":"Hotfixes: October 16, 2026","id":24307310,' \
        '"slug":"hotfixes-october-16-2026","url":"/news/24307310/hotfixes-october-16-2026"}]}}'
    base = "https://worldofwarcraft.blizzard.com/en-us/news"
    want = "https://worldofwarcraft.blizzard.com/en-us/news/24307310/hotfixes-october-16-2026"
    assert newest_hotfix_url(listing, base) == want
    assert newest_hotfix_url('<a href="/news/24307310/hotfixes-october-16-2026">', base) == want
    assert newest_hotfix_url("<html>no hotfixes</html>", base) is None


def test_parse_hotfix_article_classes_block():
    html = (FIXTURES / "hotfixes_article.html").read_text()
    feed = parse_hotfix_article(html, "https://example.test/hotfixes")
    assert feed.latest_at == datetime(2026, 10, 17, 1, 37, 29, tzinfo=UTC)  # dateModified
    entries = {(e.date, e.class_name): e.specs for e in feed.entries}
    assert entries[("October 16, 2026", "Mage")] == []  # no spec heading ⇒ whole class
    assert entries[("October 14, 2026", "Druid")] == ["Guardian", "Restoration"]
    assert entries[("October 14, 2026", "DemonHunter")] == ["Devourer"]
    # Classic sections and non-class sections are ignored.
    assert not any(cls == "Warrior" for _, cls in entries)
    assert ("October 16, 2026", "MurderRow") not in entries


def test_hotfix_touches_spec():
    feed = parse_hotfix_article((FIXTURES / "hotfixes_article.html").read_text())
    # Mage changed as a whole class on Oct 16: capped at the article's modified time.
    assert hotfix_touch_time(feed, "Mage", "Fire") == datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
    assert hotfix_touch_time(feed, "Druid", "Guardian") == datetime(2026, 10, 15, tzinfo=UTC)
    assert hotfix_touch_time(feed, "Druid", "Balance") is None
    assert hotfix_touch_time(feed, "Warrior", "Protection") is None  # Classic-only
    assert hotfix_touch_time(None, "Mage", "Fire") is None
    everyone = HotfixFeed(latest_at=datetime(2026, 10, 17, tzinfo=UTC), touches_all_classes=True)
    assert hotfix_touch_time(everyone, "Rogue", "Outlaw") == datetime(2026, 10, 17, tzinfo=UTC)


# --- build_briefing ---------------------------------------------------------------------


def _sources(monkeypatch, version, feed):
    async def fake_version():
        return version

    async def fake_feed():
        return feed

    monkeypatch.setattr(briefing, "fetch_live_version", fake_version)
    monkeypatch.setattr(briefing, "fetch_hotfix_feed", fake_feed)


_LIVE = LiveVersion(region="us", version="12.1.5.70448", build_id=70448, fetched_at=datetime.now(UTC))
_FEED = HotfixFeed(
    latest_at=datetime(2026, 10, 17, tzinfo=UTC),
    entries=[HotfixEntry(date="October 16, 2026", class_name="Mage", specs=["Fire"])],
)


async def test_briefing_uses_the_exact_build_and_live_context(monkeypatch):
    install(monkeypatch, lambda q, v: MENU_PAYLOAD)
    _sources(monkeypatch, _LIVE, _FEED)
    b = await build_briefing("Mage", "Fire", "raid")
    assert b.live_patch == "12.1.5" and b.live_build == "12.1.5.70448"
    assert b.raid_tier == "The Venomous Abyss" and b.mplus_season == "Mythic+ Season 2"
    assert b.hotfix_touches_spec is True and b.latest_hotfix_at == _FEED.latest_at
    assert b.class_display == "Mage" and b.role == "dps" and "Frost" in b.class_specs
    assert (b.product, b.environment) == ("retail", "live")
    assert abs((datetime.now(UTC) - b.now_utc).total_seconds()) < 60


async def test_briefing_falls_back_to_the_wcl_partition(monkeypatch):
    install(monkeypatch, lambda q, v: MENU_PAYLOAD)
    _sources(monkeypatch, None, None)
    b = await build_briefing("Mage", "Frost", "raid")
    assert b.live_patch == "12.1" and b.live_build is None
    assert b.latest_hotfix_at is None and b.hotfix_touches_spec is False


async def test_unknown_patch_postpones(monkeypatch):
    def boom(q, v):
        raise RuntimeError("no WCL")

    install(monkeypatch, boom)
    _sources(monkeypatch, None, None)
    with pytest.raises(PatchUnknown):
        await build_briefing("Mage", "Fire", "raid")


async def test_mplus_needs_a_season(monkeypatch):
    raids_only = {"data": {"worldData": {"zones": MENU_PAYLOAD["data"]["worldData"]["zones"][1:]}}}
    install(monkeypatch, lambda q, v: raids_only)
    _sources(monkeypatch, _LIVE, None)
    with pytest.raises(SeasonUnknown):
        await build_briefing("Mage", "Fire", "mplus")
    assert (await build_briefing("Mage", "Fire", "raid")).mplus_season is None
