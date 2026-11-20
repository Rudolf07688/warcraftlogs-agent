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


# F6 (SPEC-004, BUG-003): a Claude call's tiny thought chunks still give a status line. The slot
# is spent only on a chunk that can yield a line, and a line held back by the throttle goes out
# when the call ends (its final event or tool call), never after answer text.
async def _thinking(monkeypatch, events, step):
    from backend.tests.test_080_thinking_runner import _lines, _records

    return _lines(await _records(monkeypatch, events, step=step))


def _claude_call(chunks, final_text, call_id="c1"):
    from backend.tests.test_080_thinking_runner import _call, _event, _thought

    return [
        *(_event(_thought(c), partial=True) for c in chunks),
        _event(_thought(final_text), _call(call_id)),
    ]


def _after(call_id="c1"):
    from backend.tests.test_080_thinking_runner import _event, _response, _text

    return [_event(_response(call_id)), _event(_text("Ok."), final=True)]


async def test_an_unfinished_first_chunk_does_not_use_up_the_slot(monkeypatch):
    chunks = ["I am", " comparing", " the death", " times.", " Next"]
    events = [*_claude_call(chunks, "".join(chunks)), *_after()]
    # 0.1 s apart: the old throttle spent the slot on "I am" and skipped the rest of the call.
    assert await _thinking(monkeypatch, events, step=0.1) == ["I am comparing the death times."]


async def test_a_held_back_line_is_sent_when_the_call_ends(monkeypatch):
    # No sentence end before the call's final event: the line comes out at the call's end.
    events = [*_claude_call(["Checking", " the pulls and the deaths of the night in order of time, then"],
                            "unused"), *_after()]
    lines = await _thinking(monkeypatch, events, step=0.1)
    assert lines == ["Checking the pulls and the deaths of the night in order of time, then"]
    # A newer sentence the throttle held back within the second is sent at the tool call.
    events = [*_claude_call(["First thought.\n\n", "Second thought."], "unused"), *_after()]
    assert await _thinking(monkeypatch, events, step=0.1) == ["First thought.", "Second thought."]
    # A final event that carries only the call (no repeated thought) ends the call too.
    from backend.tests.test_080_thinking_runner import _call, _event, _thought

    events = [_event(_thought("First thought.\n\n"), partial=True),
              _event(_thought("Second thought."), partial=True), _event(_call("c1")), *_after()]
    assert await _thinking(monkeypatch, events, step=0.1) == ["First thought.", "Second thought."]


async def test_a_held_back_line_is_dropped_once_the_answer_has_started(monkeypatch):
    from backend.tests.test_080_thinking_runner import _event, _text, _thought

    events = [
        _event(_thought("First thought.\n\n"), partial=True),
        _event(_thought("Second thought."), partial=True),
        _event(_text("Vagxsu topped damage."), partial=True),
        _event(_thought("First thought. Second thought."), _text("Vagxsu topped damage."), final=True),
    ]
    assert await _thinking(monkeypatch, events, step=0.1) == ["First thought."]
    # Answer text kept at the tool call (longer than an interim): no status after it either.
    from backend.tests.test_080_thinking_runner import _call

    events = [_event(_thought("Checking"), partial=True), _event(_text("Vagxsu " * 120), partial=True),
              _event(_call("c1")), *_after()]
    assert await _thinking(monkeypatch, events, step=0.1) == []


async def test_the_clean_up_stays_at_most_once_a_second_with_the_call_end_flush(monkeypatch):
    from backend.app import agent_runner

    calls: list[str] = []
    real = agent_runner._status_line
    monkeypatch.setattr(agent_runner, "_status_line", lambda t, **kw: calls.append(t) or real(t, **kw))
    # 100 tiny chunks in 1 s (SEC-003), then the call ends: one clean-up while streaming, one at the end.
    lines = await _thinking(monkeypatch, [*_claude_call(["abc. "] * 100, "unused"), *_after()], step=0.01)
    assert len(calls) == 2
    assert lines == ["abc."]
