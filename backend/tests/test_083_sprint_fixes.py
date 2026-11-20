"""Feature 083: the sprint 2026-11-20 QA fix round (F1..F6)."""

from __future__ import annotations

import json

import pytest

from wcl_agent.agent import _INSTRUCTION_BODY


def _section(name: str) -> str:
    return _INSTRUCTION_BODY.split(f"<{name}>")[1].split(f"</{name}>")[0]


# F1 (SPEC-001): "the Ula'tek heart" is a mechanic question first, not a vague log request.
def test_boss_plus_part_word_is_a_mechanic_lookup_not_a_vague_request():
    routing = _section("ANALYSIS_ROUTING")
    mechanics = routing.split("External mechanics question:")[1].split("\n\n")[0]
    assert "the Ula'tek heart" in " ".join(mechanics.split())
    assert "get_boss_mechanics" in mechanics
    # The default rule no longer offers the same phrase as a kill to pick: one rule, not two.
    assert "Ula'tek heart" not in " ".join(_section("CONTEXT_RESOLUTION").split())


# F2 (SPEC-002, L5): the two clauses 082 cut out of scope are back.
def test_persona_settles_facts_first_and_unrelated_questions_stay_unnarrowed():
    assert "Settle the facts, confidence, and fixes first; then voice them." in " ".join(
        _section("PERSONALITY").split()
    )
    assert "population-level or unrelated questions" in " ".join(
        _section("CONTEXT_RESOLUTION").split()
    )


# F3 (BUG-001): the class fill compares realms by slug, so "Tarren Mill" finds "tarren-mill".
def test_class_fill_matches_a_stored_player_by_realm_slug():
    from backend.app.db.models import KnownPlayer, UserCharacter
    from backend.app.services.profile_context import build_preamble

    own = UserCharacter(
        role="self", name="Traecie", server="Tarren Mill", region="EU",
        class_name=None, active_spec="Frost",
    )
    seen = KnownPlayer(
        name="Traecie", server="tarren-mill", region="EU", class_name="Mage", spec="Frost"
    )
    out = build_preamble([own], [], None, known_players=[seen])
    assert "Traecie-Tarren Mill (EU) — Mage — Frost" in out


# F4 (BUG-002): difficulty words around the boss name don't turn a hit into a miss.
@pytest.mark.parametrize(
    "encounter", ["Ula'tek (Mythic)", "Mythic Ula'tek", "[Heroic] Ula'tek", "Ula'tek - LFR"]
)
async def test_boss_mechanics_ignores_difficulty_words_in_the_encounter(encounter):
    from backend.app.agent_tools.mechanics import get_boss_mechanics

    hit = await get_boss_mechanics("Venomous Heart", encounter)
    assert hit["found"] is True
    assert (hit["encounter"], hit["ability"]) == ("Ula'tek", "Venomous Heart")


# F5 (SPEC-003): whole-report participants stored before 078, under the old fightIDs: null
# query, still reach the Raids page (read-only fallback; the tools never send that query again).
LEGACY_PARTICIPANTS = (
    "query ReportQ($code: String!, $fightIDs: [Int]) { reportData { report(code: $code) "
    "{ endTime region { slug } playerDetails(fightIDs: $fightIDs) } } }"
)


async def test_participants_stored_under_the_pre_078_key_are_still_read(as_user, patched_db, monkeypatch):
    from datetime import UTC, datetime

    from backend.app.services.fetch_persistence import PendingWrite, store_batch
    from backend.tests.test_072_raid_summary import DPS, get, new_code, refuse, track
    from backend.tests.wcl_fakes import install
    from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

    code = new_code()
    variables = {"code": code, "fightIDs": None}
    body = {"data": {"reportData": {"report": {
        "endTime": 1, "region": {"slug": "eu"},
        "playerDetails": {"data": {"playerDetails": {"tanks": [], "healers": [], "dps": DPS}}},
    }}}}
    row = FetchedResponse(
        _flight_key(LEGACY_PARTICIPANTS, variables), LEGACY_PARTICIPANTS, variables,
        json.dumps(body).encode(), datetime.now(UTC),
    )
    await store_batch([PendingWrite(row, as_user.tenant_id)])
    await track(patched_db, as_user.tenant_id, code)
    fake = install(monkeypatch, refuse)

    out = (await get(as_user, code)).json()

    assert out["participants"] == [{"name": "Thrall", "class_name": "Shaman", "spec": "Enhancement", "role": "dps"}]
    assert fake.calls == []  # read from the store only: the old query is never sent
