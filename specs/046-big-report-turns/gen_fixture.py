"""Generate the deterministic 20-player Heroic kill table fixture (feature 046)."""
import json, random, sys

rng = random.Random(46)
ROSTER = [
    ("Vagxsu", "Mage", "Fire", "dps"), ("Thornak", "Warrior", "Protection", "tank"),
    ("Ellune", "Paladin", "Holy", "healer"), ("Brakka", "DeathKnight", "Blood", "tank"),
    ("Sylvae", "Druid", "Restoration", "healer"), ("Morrigan", "Priest", "Discipline", "healer"),
    ("Zhaolin", "Monk", "Mistweaver", "healer"), ("Kaelthar", "Warlock", "Destruction", "dps"),
    ("Ryssa", "Hunter", "BeastMastery", "dps"), ("Dravok", "Rogue", "Assassination", "dps"),
    ("Ishana", "Shaman", "Elemental", "dps"), ("Grumhild", "Warrior", "Fury", "dps"),
    ("Veyra", "DemonHunter", "Havoc", "dps"), ("Ostrik", "Paladin", "Retribution", "dps"),
    ("Nymeris", "Evoker", "Devastation", "dps"), ("Tavrin", "Hunter", "Marksmanship", "dps"),
    ("Lunaya", "Druid", "Balance", "dps"), ("Quellan", "Mage", "Frost", "dps"),
    ("Hesk", "DeathKnight", "Unholy", "dps"), ("Pyrelle", "Priest", "Shadow", "dps"),
]
TOTAL_TIME = 312_448
SLOTS = range(16)


def gear():
    return [
        {"id": 212000 + rng.randrange(9000), "slot": s, "quality": 4, "icon": f"inv_armor_raid_{s:02d}.jpg",
         "name": f"Gilded Raid Piece of the Ascendant {s}", "itemLevel": rng.choice([636, 639, 642, 645]),
         "bonusIDs": [rng.randrange(10000, 12000) for _ in range(5)],
         "gems": [{"id": 213000 + rng.randrange(400), "itemLevel": 610, "icon": "inv_jewelcrafting_gem.jpg"}],
         "permanentEnchant": rng.randrange(7000, 7600), "permanentEnchantName": "Enchant of Radiant Power"}
        for s in SLOTS
    ]


def talents():
    return [{"name": f"Talent Node {i}", "guid": 380000 + rng.randrange(20000), "type": 0,
             "abilityIcon": f"ability_talent_{i:02d}.jpg", "flags": 0} for i in range(42)]


def abilities():
    return [{"name": f"Spell Strike {i}", "total": rng.randrange(1_000_000, 40_000_000), "type": rng.choice([1, 4, 8, 32]),
             "abilityIcon": f"spell_strike_{i:02d}.jpg"} for i in range(12)]


def damage_done():
    entries = []
    for pid, (name, cls, spec, role) in enumerate(ROSTER, start=10):
        scale = {"dps": 1.0, "tank": 0.45, "healer": 0.12}[role]
        total = int(rng.uniform(180e6, 330e6) * scale)
        entries.append({
            "name": name, "id": pid, "guid": 240000000 + pid, "type": cls, "icon": f"{cls}-{spec}",
            "itemLevel": round(rng.uniform(636, 642), 2), "total": total,
            "activeTime": rng.randrange(250_000, TOTAL_TIME), "activeTimeReduced": rng.randrange(250_000, TOTAL_TIME),
            "abilities": abilities(), "damageAbilities": [],
            "targets": [{"name": "Queen Ansurek", "total": int(total * 0.8), "type": "Boss"},
                        {"name": "Ascended Voidspeaker", "total": int(total * 0.2), "type": "NPC"}],
            "talents": talents(), "gear": gear(),
            "pets": [{"name": "Water Elemental", "id": 400 + pid, "guid": 78116, "type": "Pet", "icon": "Pet", "total": 1000}],
        })
    rng.shuffle(entries)  # WCL order is not guaranteed; the projection sorts
    return {"data": {"entries": entries, "totalTime": TOTAL_TIME, "itemLevel": 639.4, "logVersion": 2, "gameVersion": 1}}


def summary():
    players = list(enumerate(ROSTER, start=10))
    def row(pid, name, cls, spec, total):
        return {"name": name, "id": pid, "guid": 240000000 + pid, "type": cls, "icon": f"{cls}-{spec}", "total": total}
    details = {"tanks": [], "healers": [], "dps": []}
    for pid, (name, cls, spec, role) in players:
        details[role + "s" if role != "dps" else "dps"].append({
            "name": name, "id": pid, "guid": 240000000 + pid, "type": cls, "server": "Silvermoon", "region": "EU",
            "icon": f"{cls}-{spec}", "specs": [{"spec": spec, "count": 1}], "minItemLevel": 636, "maxItemLevel": 645,
            "potionUse": rng.randrange(0, 3), "healthstoneUse": rng.randrange(0, 2),
            "combatantInfo": {"stats": {k: {"min": rng.randrange(1000, 20000), "max": rng.randrange(20000, 30000)}
                                        for k in ("Strength", "Agility", "Intellect", "Stamina", "Crit", "Haste", "Mastery", "Versatility")},
                              "talents": talents(), "gear": gear()},
        })
    return {"data": {
        "totalTime": TOTAL_TIME, "itemLevel": 639.4, "logVersion": 2, "gameVersion": 1,
        "composition": [{"name": n, "id": pid, "guid": 240000000 + pid, "type": c, "specs": [{"spec": s, "role": r}]}
                        for pid, (n, c, s, r) in players],
        "damageDone": [row(pid, n, c, s, rng.randrange(40_000_000, 330_000_000)) for pid, (n, c, s, r) in players],
        "healingDone": [row(pid, n, c, s, rng.randrange(5_000_000, 260_000_000)) for pid, (n, c, s, r) in players],
        "damageTaken": [{"name": f"Boss Ability {i}", "guid": 437000 + i, "type": 32, "abilityIcon": f"boss_{i}.jpg",
                         "total": rng.randrange(1_000_000, 90_000_000)} for i in range(30)],
        "deathEvents": [{"name": ROSTER[i][0], "id": 10 + i, "guid": 240000010 + i, "type": ROSTER[i][1],
                         "icon": f"{ROSTER[i][1]}-{ROSTER[i][2]}", "deathTime": rng.randrange(60_000, TOTAL_TIME),
                         "ability": {"name": "Reactive Toxin", "guid": 437592, "type": 8, "abilityIcon": "toxin.jpg"}}
                        for i in (8, 15, 19)],
        "playerDetails": details,
    }}


json.dump({"_note": "Synthetic, deterministic (seed 46) 20-player Heroic kill tables in the WCL v2 table shape "
                    "(feature 046). Regenerate: python3 specs/046-big-report-turns/gen_fixture.py <out>; no live data.",
           "DamageDone": damage_done(), "Summary": summary()},
          open(sys.argv[1], "w"), separators=(",", ":"))
