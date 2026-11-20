"""Feature 082 (sc-575): the coach acts on a default, and the player context carries the class."""

from __future__ import annotations

from backend.app.db.models import KnownPlayer, UserCharacter
from backend.app.services.profile_context import build_preamble


def _own(name="Traecie", server="Tarren Mill", region="EU", class_name=None, spec="Frost"):
    return UserCharacter(
        role="self", name=name, server=server, region=region,
        class_name=class_name, active_spec=spec,
    )


def _seen(name="Traecie", server="Tarren Mill", region="EU", class_name="Mage", spec="Frost"):
    return KnownPlayer(name=name, server=server, region=region, class_name=class_name, spec=spec)


def test_a_character_saved_without_a_class_takes_it_from_the_stored_player():
    """The live miss: the line read 'Traecie-Tarren Mill (EU) — Frost', so the agent asked."""
    text = build_preamble([_own()], [], None, known_players=[_seen()])
    assert "- You (self): Traecie-Tarren Mill (EU) — Mage — Frost" in text


def test_the_class_never_comes_from_a_same_named_player_on_another_realm():
    other = _seen(server="Draenor", class_name="Death Knight")
    text = build_preamble([_own()], [], None, known_players=[other])
    assert "- You (self): Traecie-Tarren Mill (EU) — Frost" in text


def test_a_saved_class_wins_over_the_stored_player():
    text = build_preamble([_own(class_name="Mage")], [], None, known_players=[_seen(class_name="Priest")])
    assert "Mage — Frost" in text and "Priest" not in text


def test_friend_without_a_class_is_filled_too():
    friend = UserCharacter(role="friend", name="Aggra", server="Draenor", region="EU", active_spec="Holy")
    text = build_preamble([], [friend], None, known_players=[_seen("Aggra", "Draenor", "EU", "Paladin", "Holy")])
    assert "Aggra-Draenor (EU) — Paladin — Holy" in text


def test_main_class_and_spec_are_listed_even_with_no_character():
    text = build_preamble([], [], None, main_class="Mage", main_spec="Frost")
    assert "KNOWN PLAYER CONTEXT" in text
    assert "- Main class/spec (profile settings): Mage — Frost" in text


def test_no_main_and_no_stored_player_leaves_the_output_unchanged():
    own = [_own(class_name="Mage")]
    assert build_preamble(own, [], None) == build_preamble(own, [], None, main_class=None, main_spec=None)
    assert "Main class/spec" not in build_preamble(own, [], None)


def test_a_turn_with_no_profile_data_still_has_an_empty_preamble():
    # "No regression": nothing known at all stays a bare question for the agent to ask.
    assert build_preamble([], [], None, main_class=None, main_spec=None) == ""


def test_mechanics_question_routes_to_get_boss_mechanics():
    """contract:mechanics-tool (consumer side): the routing line names the tool."""
    from wcl_agent.agent import _INSTRUCTION_BODY

    routing = _INSTRUCTION_BODY.split("<ANALYSIS_ROUTING>")[1].split("</ANALYSIS_ROUTING>")[0]
    line = routing.split("External mechanics question:")[1].split("\n\n")[0]
    assert "get_boss_mechanics" in line
