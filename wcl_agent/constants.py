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


def normalize_class_name(name: str) -> str | None:
    """Map a loose class name (any casing/spacing) to its filter value.

    Returns None if it can't be matched.
    """
    key = name.replace(" ", "").replace("'", "").lower()
    for filter_value in CLASS_SPECS:
        if filter_value.lower() == key:
            return filter_value
    return None
