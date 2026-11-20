"""Feature 083: the sprint 2026-11-20 QA fix round (F1..F6)."""

from __future__ import annotations

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
