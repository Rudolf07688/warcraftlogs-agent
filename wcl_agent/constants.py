"""Static WoW reference data used to build correct API filters.

Warcraft Logs' ``className`` / ``specName`` filters expect PascalCase,
space-free identifiers (e.g. ``Hunter`` / ``BeastMastery``) rather than the
localized display names. This map is the single source of truth for that.
"""

# class filter value -> {display name, [spec filter values]}
CLASS_SPECS: dict[str, dict[str, object]] = {
    "DeathKnight": {"display": "Death Knight", "specs": ["Blood", "Frost", "Unholy"]},
    "DemonHunter": {"display": "Demon Hunter", "specs": ["Havoc", "Vengeance"]},
    "Druid": {"display": "Druid", "specs": ["Balance", "Feral", "Guardian", "Restoration"]},
    "Evoker": {"display": "Evoker", "specs": ["Augmentation", "Devastation", "Preservation"]},
    "Hunter": {"display": "Hunter", "specs": ["BeastMastery", "Marksmanship", "Survival"]},
    "Mage": {"display": "Mage", "specs": ["Arcane", "Fire", "Frost"]},
    "Monk": {"display": "Monk", "specs": ["Brewmaster", "Mistweaver", "Windwalker"]},
    "Paladin": {"display": "Paladin", "specs": ["Holy", "Protection", "Retribution"]},
    "Priest": {"display": "Priest", "specs": ["Discipline", "Holy", "Shadow"]},
    "Rogue": {"display": "Rogue", "specs": ["Assassination", "Outlaw", "Subtlety"]},
    "Shaman": {"display": "Shaman", "specs": ["Elemental", "Enhancement", "Restoration"]},
    "Warlock": {"display": "Warlock", "specs": ["Affliction", "Demonology", "Destruction"]},
    "Warrior": {"display": "Warrior", "specs": ["Arms", "Fury", "Protection"]},
}

# Accepted metric values (WoW-relevant subset of CharacterRankingMetricType).
METRICS = ["dps", "hps", "wdps", "rdps", "bossdps", "default"]

# Raid-role mapping (feature 007 / US4): the single source of truth for inferring a
# character's Tank/Healer/DPS role from its WCL spec filter value. Spec names are
# role-unambiguous across classes (e.g. Holy=healer for Paladin & Priest; Protection=
# tank for Paladin & Warrior), so a flat spec→role map is sufficient. Every spec not
# listed as a tank or healer below is damage.
_TANK_SPECS = {"Blood", "Vengeance", "Guardian", "Brewmaster", "Protection"}
_HEALER_SPECS = {"Restoration", "Preservation", "Mistweaver", "Holy", "Discipline"}

SPEC_ROLES: dict[str, str] = {}
for _cls in CLASS_SPECS.values():
    for _spec in _cls["specs"]:  # type: ignore[attr-defined]
        if _spec in _TANK_SPECS:
            SPEC_ROLES[_spec] = "tank"
        elif _spec in _HEALER_SPECS:
            SPEC_ROLES[_spec] = "healer"
        else:
            SPEC_ROLES[_spec] = "dps"


def role_for_spec(spec: str | None) -> str | None:
    """Return 'tank' | 'healer' | 'dps' for a known spec; None when unknown/unset.

    Unknown or missing specs return None (unset, not guessed) so an unresolved character
    simply shows no role (FR-025).
    """
    if not spec:
        return None
    return SPEC_ROLES.get(spec)


def normalize_class_name(name: str) -> str | None:
    """Map a loose class name (any casing/spacing) to its filter value.

    Returns None if it can't be matched.
    """
    key = name.replace(" ", "").replace("'", "").lower()
    for filter_value in CLASS_SPECS:
        if filter_value.lower() == key:
            return filter_value
    return None
