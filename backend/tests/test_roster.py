"""Live class/spec roster from Warcraft Logs game data (feature 015, US3)."""

from __future__ import annotations

import pytest

from backend.tests.wcl_fakes import install
from wcl_agent import roster
from wcl_agent.constants import normalize_class_name, role_for_spec
from wcl_agent.tools import get_spec_options


def _payload(extra_dh: list[dict] | None = None, drop: str | None = None) -> dict:
    dh_specs = [
        {"id": 1, "name": "Havoc", "slug": "Havoc"},
        {"id": 2, "name": "Vengeance", "slug": "Vengeance"},
        {"id": 3, "name": "Devourer", "slug": "Devourer"},
    ] + (extra_dh or [])
    classes = [
        {"id": 12, "name": "Demon Hunter", "slug": "DemonHunter", "specs": dh_specs},
        {"id": 3, "name": "Hunter", "slug": "Hunter", "specs": [
            {"id": 1, "name": "Beast Mastery", "slug": "BeastMastery"},
            {"id": 2, "name": "Marksmanship", "slug": "Marksmanship"},
            {"id": 3, "name": "Survival", "slug": "Survival"},
        ]},
        {"id": 11, "name": "Warrior", "slug": "Warrior", "specs": [
            {"id": 1, "name": "Arms", "slug": "Arms"},
            {"id": 2, "name": "Fury", "slug": "Fury"},
            {"id": 3, "name": "Protection", "slug": "Protection"},
        ]},
    ]
    for c in classes:
        c["specs"] = [s for s in c["specs"] if s["slug"] != drop]
    return {"data": {"gameData": {"classes": classes}}}


@pytest.fixture(autouse=True)
def _fresh_roster():
    roster._reset_for_tests()
    yield
    roster._reset_for_tests()


async def test_game_data_maps_slugs_and_includes_devourer(monkeypatch):
    fake = install(monkeypatch, lambda q, v: _payload())
    r = await roster.load_roster()
    assert r.source == "game_data" and fake.count("GameClasses") == 1
    assert r.specs_for("DemonHunter") == ["Havoc", "Vengeance", "Devourer"]
    devourer = r.get("DemonHunter", "Devourer")
    assert devourer.class_display == "Demon Hunter" and devourer.role == "dps"
    assert r.get("Hunter", "BeastMastery").spec_display == "Beast Mastery"
    assert r.get("DemonHunter", "Vengeance").role == "tank"
    assert roster.roster_snapshot() is r  # becomes the process snapshot


async def test_fallback_on_error_still_lists_devourer(monkeypatch):
    def boom(q, v):
        raise RuntimeError("WCL down")

    install(monkeypatch, boom)
    r = await roster.load_roster()
    assert r.source == "fallback"
    assert "Devourer" in r.specs_for("DemonHunter")
    assert len(r.specs) == 40


def test_snapshot_before_any_load_is_the_fallback():
    snap = roster.roster_snapshot()
    assert snap.source == "fallback" and snap.has("DemonHunter", "Devourer")


async def test_new_spec_appears_and_removed_spec_disappears(monkeypatch):
    install(monkeypatch, lambda q, v: _payload(
        extra_dh=[{"id": 4, "name": "Felscarred", "slug": "Felscarred"}], drop="Survival"))
    r = await roster.load_roster()
    assert r.has("DemonHunter", "Felscarred") and r.get("DemonHunter", "Felscarred").role == "dps"
    assert not r.has("Hunter", "Survival")
    # The new spec is known everywhere the roster is used.
    assert role_for_spec("Felscarred") == "dps"
    options = await get_spec_options("Demon Hunter")
    assert "Felscarred" in options["specs"]


def test_role_for_devourer_and_unknown():
    assert role_for_spec("Devourer") == "dps"
    assert role_for_spec("NotASpec") is None
    assert normalize_class_name("demon hunter") == "DemonHunter"
