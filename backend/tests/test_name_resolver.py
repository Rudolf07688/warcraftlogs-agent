"""The shared name resolver (feature 044, sc-304): specs/044-kb-search/contracts/name-resolver.md."""

from __future__ import annotations

import pytest

from backend.app.db import repository as repo
from backend.app.db.models import UserCharacter
from backend.app.services import name_resolver as nr
from backend.app.services.name_resolver import (
    ClassSpec,
    ResolutionError,
    name_key,
    resolve_character,
    resolve_class,
    resolve_class_spec,
    resolve_difficulty,
    resolve_encounter,
    spec_pairs,
)

ZONES = [
    {
        "id": 46,
        "name": "The Venomous Abyss",
        "encounters": [
            {"id": 3101, "name": "Ula'tek"},
            {"id": 3102, "name": "Queen Ansurek"},
            {"id": 3103, "name": "Queen Ylva"},
        ],
    },
    # The same boss listed again (another partition zone) must not make it ambiguous.
    {"id": 47, "name": "Fated Abyss", "encounters": [{"id": 3101, "name": "Ula'tek"}]},
]


@pytest.fixture
def zones(monkeypatch):
    async def load():
        return ZONES

    monkeypatch.setattr(nr, "load_world_zones", load)


# --- name_key -----------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["Ula'tek", "ulatek", "ULATEK", "Úla-tek", "ula tek", " Ula’tek "])
def test_name_key_ignores_case_accents_apostrophes_spaces_and_hyphens(raw):
    assert name_key(raw) == "ulatek"


def test_name_key_keeps_digits_and_non_latin_letters():
    assert name_key("Mök2") == "mok2"
    assert name_key("Лилия") == "лилия"


# --- classes and specs (AC2: one test per abbreviation) -----------------------------------


@pytest.mark.parametrize(
    ("alias", "class_name"), [("warr", "Warrior"), ("dh", "DemonHunter"), ("dk", "DeathKnight")]
)
def test_class_abbreviation(alias, class_name):
    assert resolve_class(alias) == class_name
    assert resolve_class_spec(alias) == ClassSpec(class_name, None, None)


def test_ret_abbreviation():
    assert spec_pairs("ret") == (ClassSpec("Paladin", "Retribution", "dps"),)
    assert resolve_class_spec("ret") == ClassSpec("Paladin", "Retribution", "dps")


def test_prot_abbreviation():
    assert set(spec_pairs("prot")) == {
        ClassSpec("Paladin", "Protection", "tank"),
        ClassSpec("Warrior", "Protection", "tank"),
    }
    assert resolve_class_spec("prot", class_name="pally") == ClassSpec("Paladin", "Protection", "tank")


def test_resto_abbreviation():
    assert {p.class_name for p in spec_pairs("resto")} == {"Druid", "Shaman"}
    assert resolve_class_spec("resto sham") == ClassSpec("Shaman", "Restoration", "healer")


def test_disc_abbreviation():
    assert resolve_class_spec("disc") == ClassSpec("Priest", "Discipline", "healer")


def test_bm_abbreviation():
    assert resolve_class_spec("bm") == ClassSpec("Hunter", "BeastMastery", "dps")


def test_mm_abbreviation():
    assert resolve_class_spec("mm") == ClassSpec("Hunter", "Marksmanship", "dps")


def test_sv_abbreviation():
    assert resolve_class_spec("sv") == ClassSpec("Hunter", "Survival", "dps")


@pytest.mark.parametrize(
    "phrase", ["arms warr", "Arms Warrior", "warrior arms", "ARMS-WARR", "arms war"]
)
def test_arms_warr_gives_warrior_arms(phrase):
    assert resolve_class_spec(phrase) == ClassSpec("Warrior", "Arms", "dps")


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("bm hunter", ClassSpec("Hunter", "BeastMastery", "dps")),
        ("beast mastery hunter", ClassSpec("Hunter", "BeastMastery", "dps")),
        ("death knight", ClassSpec("DeathKnight", None, None)),
        ("bdk", ClassSpec("DeathKnight", "Blood", "tank")),
        ("frost mage", ClassSpec("Mage", "Frost", "dps")),
        ("holy priest", ClassSpec("Priest", "Holy", "healer")),
    ],
)
def test_class_spec_phrases(phrase, expected):
    assert resolve_class_spec(phrase) == expected


def test_prot_without_class_is_ambiguous_where_one_answer_is_required():
    with pytest.raises(ResolutionError) as err:
        resolve_class_spec("prot")
    assert err.value.reason == "ambiguous"
    assert err.value.field == "spec"
    assert set(err.value.matches) == {"Paladin / Protection", "Warrior / Protection"}
    assert "Say which one" in str(err.value)


def test_spec_only_filter_gives_every_class_with_the_spec():
    assert {p.class_name for p in spec_pairs("Holy")} == {"Paladin", "Priest"}
    assert spec_pairs("Holy", class_name="priest") == (ClassSpec("Priest", "Holy", "healer"),)


def test_spec_the_class_lacks_is_a_correctable_error():
    with pytest.raises(ResolutionError) as err:
        spec_pairs("Holy", class_name="Warrior")
    assert err.value.reason == "unknown"
    with pytest.raises(ResolutionError):
        resolve_class_spec("holy", class_name="warr")


@pytest.mark.parametrize(
    ("call", "field", "close"),
    [
        (lambda: resolve_class("warior"), "class", "Warrior"),
        (lambda: spec_pairs("retribtion"), "spec", "Retribution"),
        (lambda: resolve_class_spec("assasination"), "spec", "Assassination"),
    ],
)
def test_typos_are_unknown_with_close_matches(call, field, close):
    with pytest.raises(ResolutionError) as err:
        call()
    assert (err.value.field, err.value.reason) == (field, "unknown")
    assert close in err.value.matches
    assert close in str(err.value)


def test_empty_values_never_match():
    with pytest.raises(ResolutionError):
        resolve_class("")
    with pytest.raises(ResolutionError):
        spec_pairs("'")
    with pytest.raises(ResolutionError):
        resolve_class_spec("  ")


# --- difficulty ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("hc", 4), ("Heroic", 4), (4, 4), ("4", 4), ("mythic", 5), ("M", 5), ("normal", 3),
        ("LFR", 1), ("m+", 10), ("Mythic+", 10), ("mplus", 10), (10, 10),
    ],
)
def test_difficulty(value, expected):
    assert resolve_difficulty(value).id == expected


def test_difficulty_names_reuse_the_tool_map():
    assert resolve_difficulty("hc").name == "Heroic"
    assert resolve_difficulty("m+").name == "Mythic+"


@pytest.mark.parametrize("value", ["2", "epic", "%", ""])
def test_unknown_difficulty(value):
    with pytest.raises(ResolutionError) as err:
        resolve_difficulty(value)
    assert err.value.field == "difficulty"


# --- encounters ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["Ula'tek", "ulatek", "ULATEK", "Úlatek", "ula'"])
async def test_encounter_forms_share_one_id(zones, session, tenant_id, value):
    encounter, difficulty = await resolve_encounter(value, session=session, tenant_id=tenant_id)
    assert encounter.id == 3101
    assert encounter.zone_id == 46
    assert difficulty is None


async def test_difficulty_word_in_an_encounter_phrase(zones, session, tenant_id):
    encounter, difficulty = await resolve_encounter("heroic ulatek", session=session, tenant_id=tenant_id)
    assert encounter.id == 3101 and difficulty is not None and difficulty.id == 4
    encounter, difficulty = await resolve_encounter("Ula'tek M+", session=session, tenant_id=tenant_id)
    assert encounter.id == 3101 and difficulty.id == 10


async def test_encounter_by_id(zones, session, tenant_id):
    encounter, _ = await resolve_encounter(3102, session=session, tenant_id=tenant_id)
    assert encounter.name == "Queen Ansurek"
    with pytest.raises(ResolutionError):
        await resolve_encounter("999999", session=session, tenant_id=tenant_id)


async def test_encounter_typo_is_unknown_with_close_matches(zones, session, tenant_id):
    with pytest.raises(ResolutionError) as err:
        await resolve_encounter("Ulatk", session=session, tenant_id=tenant_id)
    assert err.value.reason == "unknown"
    assert "Ula'tek" in err.value.matches


async def test_encounter_shared_part_is_ambiguous(zones, session, tenant_id):
    with pytest.raises(ResolutionError) as err:
        await resolve_encounter("queen", session=session, tenant_id=tenant_id)
    assert err.value.reason == "ambiguous"
    assert {m.split(" (")[0] for m in err.value.matches} == {"Queen Ansurek", "Queen Ylva"}


async def test_known_encounters_resolve_when_the_zone_list_fails(
    monkeypatch, session, tenant_id, other_tenant_id
):
    async def down():
        raise RuntimeError("WCL down")

    monkeypatch.setattr(nr, "load_world_zones", down)
    await repo.upsert_known_encounter(
        session, tenant_id=tenant_id, encounter_id=3101, encounter_name="Ula'tek", zone_id=46,
        zone_name="The Venomous Abyss",
    )
    await repo.upsert_known_encounter(
        session, tenant_id=other_tenant_id, encounter_id=2902, encounter_name="Ulgrax",
    )
    encounter, _ = await resolve_encounter("ulatek", session=session, tenant_id=tenant_id)
    assert encounter.id == 3101
    with pytest.raises(ResolutionError):  # another workspace's known encounter is never read
        await resolve_encounter("ulgrax", session=session, tenant_id=tenant_id)


# --- characters ---------------------------------------------------------------------------


async def _seed_people(session, tenant_id, other_tenant_id):
    session.add_all(
        [
            UserCharacter(
                tenant_id=tenant_id, role="self", name="Vagxsu", server="Tarren Mill", region="EU",
                class_name="Warrior", active_spec="Arms",
            ),
            UserCharacter(
                tenant_id=tenant_id, role="friend", name="Lûmi", server="Silvermoon", region="EU",
                class_name="Priest", active_spec="Holy",
            ),
            UserCharacter(
                tenant_id=other_tenant_id, role="self", name="Secretone", server="Draenor",
                region="EU",
            ),
        ]
    )
    await session.flush()
    await repo.upsert_known_player(session, tenant_id=tenant_id, name="Vagxsu", server="Tarren Mill", region="EU")
    await repo.upsert_known_player(session, tenant_id=tenant_id, name="Kael", server="Draenor", region="EU")
    await repo.upsert_known_player(session, tenant_id=tenant_id, name="Kael", server="Kazzak", region="EU")


async def test_own_character_resolves_with_class_and_spec(session, tenant_id, other_tenant_id):
    await _seed_people(session, tenant_id, other_tenant_id)
    found = await resolve_character("vagxsu", session=session, tenant_id=tenant_id)
    assert (found.name, found.server, found.region) == ("Vagxsu", "Tarren Mill", "EU")
    assert (found.class_name, found.spec, found.key) == ("Warrior", "Arms", "vagxsu")


async def test_friend_resolves_accent_insensitively(session, tenant_id, other_tenant_id):
    await _seed_people(session, tenant_id, other_tenant_id)
    found = await resolve_character("LUMI", session=session, tenant_id=tenant_id)
    assert found.name == "Lûmi" and found.key == "lumi"


async def test_name_on_two_realms_is_ambiguous_until_the_realm_is_given(
    session, tenant_id, other_tenant_id
):
    await _seed_people(session, tenant_id, other_tenant_id)
    with pytest.raises(ResolutionError) as err:
        await resolve_character("Kael", session=session, tenant_id=tenant_id)
    assert err.value.reason == "ambiguous"
    assert set(err.value.matches) == {"Kael-Draenor (EU)", "Kael-Kazzak (EU)"}
    found = await resolve_character("Kael-kazzak", session=session, tenant_id=tenant_id)
    assert found.server == "Kazzak"


async def test_another_workspaces_character_is_never_resolved(session, tenant_id, other_tenant_id):
    await _seed_people(session, tenant_id, other_tenant_id)
    with pytest.raises(ResolutionError) as err:
        await resolve_character("Secretone", session=session, tenant_id=tenant_id)
    assert err.value.reason == "unknown"
    assert "Secretone" not in err.value.matches


async def test_unknown_character_names_close_matches(session, tenant_id, other_tenant_id):
    await _seed_people(session, tenant_id, other_tenant_id)
    with pytest.raises(ResolutionError) as err:
        await resolve_character("Vagxu", session=session, tenant_id=tenant_id)
    assert err.value.field == "character"
    assert "Vagxsu" in err.value.matches


def test_full_spec_name_with_a_class_uses_the_roster_match():
    assert resolve_class_spec("Beast Mastery", class_name="hunter") == ClassSpec(
        "Hunter", "BeastMastery", "dps"
    )
    assert resolve_class_spec("", class_name="dh") == ClassSpec("DemonHunter", None, None)
