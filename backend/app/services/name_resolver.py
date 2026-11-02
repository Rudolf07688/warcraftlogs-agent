"""The shared name resolver (feature 044, sc-304): loose names to canonical filter values.

One module turns what players write ("arms warr", "resto", "Ula'tek", "hc", a friend's name)
into the values the chunk writers store and the searches filter on, so both sides agree
(specs/044-kb-search/contracts/name-resolver.md). Classes and specs come from the roster
(``roster_snapshot``, ``normalize_class_name``, ``resolve_spec``); the only data added here
is a table of abbreviations, each checked against the roster when it is used. Encounters come
from the cached zone list plus the workspace's known encounters, characters from the
workspace's profile and known players.

Nothing here returns an empty match: an unknown or ambiguous value raises
:class:`ResolutionError`, whose text names the close matches so the agent can correct itself.
"""

from __future__ import annotations

import difflib
import logging
import unicodedata
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.game import constants
from wcl_agent.game.constants import normalize_class_name
from wcl_agent.game.patch import MYTHIC_PLUS_DIFFICULTY_ID
from wcl_agent.game.roster import RosterSpec, resolve_spec, roster_snapshot
from wcl_agent.menu import load_world_zones

from ..db.models import KnownEncounter, KnownPlayer, UserCharacter

logger = logging.getLogger(__name__)

MAX_MATCHES = 5
_ECHO_CHARS = 60  # the input is echoed in the error text, cut to this length
_KNOWN_PLAYERS_SCAN = 2000  # newest known players considered for a name

# Abbreviations players use. Targets are roster filter values; an alias whose target the
# roster doesn't list is ignored, so this table can never add a class or spec.
CLASS_ALIASES: dict[str, str] = {
    "warr": "Warrior", "war": "Warrior", "dh": "DemonHunter", "dk": "DeathKnight",
    "pal": "Paladin", "pala": "Paladin", "pally": "Paladin", "lock": "Warlock",
    "hunt": "Hunter", "sham": "Shaman", "shammy": "Shaman", "evo": "Evoker",
    "dru": "Druid", "rog": "Rogue",
}
SPEC_ALIASES: dict[str, str] = {
    "ret": "Retribution", "prot": "Protection", "resto": "Restoration", "disc": "Discipline",
    "bm": "BeastMastery", "mm": "Marksmanship", "sv": "Survival", "surv": "Survival",
    "arc": "Arcane", "aff": "Affliction", "affli": "Affliction", "demo": "Demonology",
    "destro": "Destruction", "enh": "Enhancement", "enhance": "Enhancement", "ele": "Elemental",
    "ww": "Windwalker", "mw": "Mistweaver", "brew": "Brewmaster", "aug": "Augmentation",
    "dev": "Devastation", "deva": "Devastation", "pres": "Preservation", "sub": "Subtlety",
    "sin": "Assassination", "sins": "Assassination", "assa": "Assassination",
    "veng": "Vengeance", "guard": "Guardian", "boomkin": "Balance", "boomy": "Balance",
}
# Spec abbreviations that already name the class.
CLASS_SPEC_ALIASES: dict[str, tuple[str, str]] = {
    "bdk": ("DeathKnight", "Blood"), "fdk": ("DeathKnight", "Frost"),
    "udk": ("DeathKnight", "Unholy"), "hpal": ("Paladin", "Holy"),
    "hpala": ("Paladin", "Holy"), "rsham": ("Shaman", "Restoration"),
}

MYTHIC_PLUS_NAME = "Mythic+"
DIFFICULTY_NAMES: dict[int, str] = {**constants.DIFFICULTY_NAMES, MYTHIC_PLUS_DIFFICULTY_ID: MYTHIC_PLUS_NAME}
_DIFFICULTY_WORDS: dict[str, int] = {
    "lfr": 1, "lookingforraid": 1, "raidfinder": 1,
    "normal": 3, "norm": 3, "nm": 3,
    "heroic": 4, "hc": 4, "hero": 4,
    "mythic": 5, "myth": 5, "m": 5,
    "mythicplus": MYTHIC_PLUS_DIFFICULTY_ID, "mplus": MYTHIC_PLUS_DIFFICULTY_ID,
    "keys": MYTHIC_PLUS_DIFFICULTY_ID, "keystone": MYTHIC_PLUS_DIFFICULTY_ID,
}

Field = Literal["class", "spec", "encounter", "difficulty", "character"]
Reason = Literal["unknown", "ambiguous"]
T = TypeVar("T")


def name_key(value: str) -> str:
    """The one normalised form of a name: accents dropped, casefolded, letters and digits only.

    "Ula'tek", "ulatek", "Úla-tek" and "ULA TEK" share a key. 043's chunk writers store it as
    ``players[].key`` / ``characters[].key``; search matches with it.
    """
    # NFKD splits "Ú" into "U" + a combining accent, which is not alphanumeric, so it drops.
    return "".join(c for c in unicodedata.normalize("NFKD", value or "").casefold() if c.isalnum())


class ResolutionError(ValueError):
    """A value that names nothing, or several things. ``str(err)`` is safe to show the agent."""

    def __init__(self, field: Field, value: str, reason: Reason, matches: Iterable[str] = ()):
        self.field = field
        self.value = value
        self.reason = reason
        self.matches = tuple(dict.fromkeys(matches))[:MAX_MATCHES]
        shown = value if len(value) <= _ECHO_CHARS else value[: _ECHO_CHARS - 1] + "…"
        if reason == "ambiguous":
            message = f'Ambiguous {field} "{shown}": it could be {", ".join(self.matches)}. Say which one.'
        else:
            message = f'Unknown {field} "{shown}".'
            if self.matches:
                message += f" Close matches: {', '.join(self.matches)}."
        super().__init__(message)


@dataclass(frozen=True)
class ClassSpec:
    class_name: str  # roster filter value, e.g. "DeathKnight"
    spec: str | None  # roster filter value, e.g. "BeastMastery"; None = the whole class
    role: str | None  # tank | healer | dps (None without a spec)


@dataclass(frozen=True)
class ResolvedDifficulty:
    id: int
    name: str


@dataclass(frozen=True)
class ResolvedEncounter:
    id: int
    name: str
    zone_id: int | None
    zone_name: str | None


@dataclass(frozen=True)
class ResolvedCharacter:
    name: str
    server: str
    region: str
    class_name: str | None
    spec: str | None
    key: str  # name_key(name)


def _close(key: str, names: Iterable[str]) -> list[str]:
    """Display names whose key is close to ``key``."""
    by_key: dict[str, str] = {}
    for name in names:
        by_key.setdefault(name_key(name), name)
    hits = difflib.get_close_matches(key, list(by_key), n=MAX_MATCHES, cutoff=0.6)
    return [by_key[h] for h in hits]


def _label(entry: RosterSpec) -> str:
    return f"{entry.class_display} / {entry.spec_display}"


# --- Classes and specs ------------------------------------------------------------------


def _class_forms(entry: RosterSpec) -> set[str]:
    forms = {name_key(entry.class_name), name_key(entry.class_display)}
    return forms | {alias for alias, target in CLASS_ALIASES.items() if target == entry.class_name}


def _spec_forms(entry: RosterSpec) -> set[str]:
    forms = {name_key(entry.spec), name_key(entry.spec_display)}
    return forms | {alias for alias, target in SPEC_ALIASES.items() if target == entry.spec}


def _class_spec(entry: RosterSpec) -> ClassSpec:
    return ClassSpec(entry.class_name, entry.spec, entry.role)


def resolve_class(value: str) -> str:
    """A class name or abbreviation ("warr", "death knight") to its roster filter value."""
    key = name_key(value)
    roster = roster_snapshot()
    target = CLASS_ALIASES.get(key)
    if target in roster.classes():
        return target
    found = normalize_class_name(key) if key else None  # "demon hunter" keys like "DemonHunter"
    if found:
        return found
    names = [*roster.classes(), *(roster.class_display(c) for c in roster.classes())]
    raise ResolutionError("class", value, "unknown", _close(key, names))


def _entries_for_spec(key: str) -> list[RosterSpec]:
    if key in CLASS_SPEC_ALIASES:
        cls, spec = CLASS_SPEC_ALIASES[key]
        entry = roster_snapshot().get(cls, spec)
        return [entry] if entry else []
    return [e for e in roster_snapshot().specs if key and key in _spec_forms(e)]


def _unknown_spec(value: str, key: str, entries: Iterable[RosterSpec]) -> ResolutionError:
    names = [n for e in entries for n in (e.spec_display, e.spec)]
    return ResolutionError("spec", value, "unknown", _close(key, names))


def resolve_class_spec(value: str, class_name: str | None = None) -> ClassSpec:
    """One class, or one class+spec, from a phrase. Use where ONE answer is required.

    "arms warr", "warrior arms", "bm hunter" and "bdk" resolve; a class alone ("warrior")
    gives ``spec=None``. A spec several classes share ("prot") is ambiguous unless
    ``class_name`` says which class.
    """
    roster = roster_snapshot()
    if class_name is not None:
        cls = resolve_class(class_name)
        if not name_key(value):
            return ClassSpec(cls, None, None)
        # The roster's own class+spec match first (full names), then the abbreviations.
        entry = resolve_spec(cls, name_key(value))
        if entry is None:
            entry = next((e for e in _entries_for_spec(name_key(value)) if e.class_name == cls), None)
        if entry is None:
            raise _unknown_spec(value, name_key(value), [e for e in roster.specs if e.class_name == cls])
        return _class_spec(entry)
    key = name_key(value)
    for entry in roster.specs:
        if key in _class_forms(entry):
            return ClassSpec(entry.class_name, None, None)
    compound = {
        (e.class_name, e.spec): e
        for e in roster.specs
        for cf in _class_forms(e)
        for sf in _spec_forms(e)
        if key in (cf + sf, sf + cf)
    }
    if len(compound) == 1:
        return _class_spec(next(iter(compound.values())))
    entries = list(compound.values()) or _entries_for_spec(key)
    if len(entries) == 1:
        return _class_spec(entries[0])
    if entries:
        raise ResolutionError("spec", value, "ambiguous", [_label(e) for e in entries])
    names = [n for e in roster.specs for n in (e.spec_display, e.class_display, _label(e))]
    raise ResolutionError("spec", value, "unknown", _close(key, names))


def spec_pairs(spec: str, class_name: str | None = None) -> tuple[ClassSpec, ...]:
    """Every (class, spec) that has this spec: the form a spec-only search filter takes.

    "holy" gives Paladin/Holy and Priest/Holy; with ``class_name`` only that class's spec, and
    a spec the class lacks is an error.
    """
    key = name_key(spec)
    entries = _entries_for_spec(key)
    if class_name is not None:
        cls = resolve_class(class_name)
        own = [e for e in roster_snapshot().specs if e.class_name == cls]
        entries = [e for e in entries if e.class_name == cls]
        if not entries:
            raise _unknown_spec(spec, key, own)
    if not entries:
        raise _unknown_spec(spec, key, roster_snapshot().specs)
    return tuple(_class_spec(e) for e in entries)


# --- Difficulty ---------------------------------------------------------------------------


def _difficulty_word(value: str) -> int | None:
    return _DIFFICULTY_WORDS.get(name_key(value.replace("+", " plus ")))


def resolve_difficulty(value: str | int) -> ResolvedDifficulty:
    """"hc", "Heroic" or 4 to 4 Heroic; "m+", "mythic+" or 10 to 10 Mythic+; LFR 1, Normal 3, Mythic 5."""
    text = str(value).strip()
    found = int(text) if text.isascii() and text.isdigit() else _difficulty_word(text)
    if found in DIFFICULTY_NAMES:
        return ResolvedDifficulty(found, DIFFICULTY_NAMES[found])
    raise ResolutionError(
        "difficulty", text, "unknown", _close(name_key(text), DIFFICULTY_NAMES.values())
    )


# --- Encounters ---------------------------------------------------------------------------


async def _encounter_candidates(
    session: AsyncSession, tenant_id: uuid.UUID | None
) -> list[ResolvedEncounter]:
    found: dict[int, ResolvedEncounter] = {}
    try:
        zones = await load_world_zones()
    except Exception as exc:  # noqa: BLE001 - the workspace's known encounters still resolve
        logger.warning("zone list unavailable for encounter resolution: %s", type(exc).__name__)
        zones = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        for enc in zone.get("encounters") or []:
            if isinstance(enc, dict) and isinstance(enc.get("id"), int) and enc.get("name"):
                found.setdefault(
                    enc["id"], ResolvedEncounter(enc["id"], enc["name"], zone.get("id"), zone.get("name"))
                )
    if tenant_id is not None:
        rows = await session.execute(
            select(
                KnownEncounter.encounter_id,
                KnownEncounter.encounter_name,
                KnownEncounter.zone_id,
                KnownEncounter.zone_name,
            ).where(KnownEncounter.tenant_id == tenant_id)
        )
        for row in rows:
            found.setdefault(row[0], ResolvedEncounter(row[0], row[1], row[2], row[3]))
    return list(found.values())


def _encounter_label(encounter: ResolvedEncounter) -> str:
    return f"{encounter.name} ({encounter.zone_name})" if encounter.zone_name else encounter.name


def _split_difficulty(value: str) -> tuple[str, ResolvedDifficulty | None]:
    """"heroic ulatek" -> ("ulatek", Heroic); a difficulty word first or last, never alone."""
    words = value.split()
    if len(words) > 1:
        for index in (0, -1):
            found = _difficulty_word(words[index])
            if found in DIFFICULTY_NAMES:
                rest = words[1:] if index == 0 else words[:-1]
                return " ".join(rest), ResolvedDifficulty(found, DIFFICULTY_NAMES[found])
    return value, None


def _one(field: Field, value: str, matches: list[T], label: Callable[[T], str]) -> T:
    if len(matches) == 1:
        return matches[0]
    raise ResolutionError(field, value, "ambiguous", [label(m) for m in matches])


async def resolve_encounter(
    value: str | int, *, session: AsyncSession, tenant_id: uuid.UUID | None
) -> tuple[ResolvedEncounter, ResolvedDifficulty | None]:
    """A boss name or id to its encounter, plus a difficulty named in the phrase.

    Names match exactly on :func:`name_key`, then as a unique part of a name. The zone list is
    the cached one every turn reads; when it can't be loaded, the workspace's known encounters
    still resolve.
    """
    text = str(value).strip()
    candidates = await _encounter_candidates(session, tenant_id)
    if text.isascii() and text.isdigit():
        by_id = [c for c in candidates if c.id == int(text)]
        if by_id:
            return by_id[0], None
        raise ResolutionError("encounter", text, "unknown")
    name, difficulty = _split_difficulty(text)
    key = name_key(name)
    exact = [c for c in candidates if key and name_key(c.name) == key]
    if exact:
        return _one("encounter", text, exact, _encounter_label), difficulty
    partial = [c for c in candidates if len(key) >= 3 and key in name_key(c.name)]
    if partial:
        return _one("encounter", text, partial, _encounter_label), difficulty
    raise ResolutionError("encounter", text, "unknown", _close(key, [c.name for c in candidates]))


# --- Characters ---------------------------------------------------------------------------


async def resolve_character(
    value: str, *, session: AsyncSession, tenant_id: uuid.UUID
) -> ResolvedCharacter:
    """A character name ("Vagxsu" or "Vagxsu-Tarren Mill") from this workspace's own characters,
    friends and known players. Other workspaces are never read (explicit tenant predicate on
    top of RLS)."""
    text = value.strip()
    name, _, realm = text.partition("-")
    key, realm_key = name_key(name), name_key(realm)
    own = await session.execute(
        select(
            UserCharacter.name, UserCharacter.server, UserCharacter.region,
            UserCharacter.class_name, UserCharacter.active_spec,
        ).where(UserCharacter.tenant_id == tenant_id)
    )
    known = await session.execute(
        select(
            KnownPlayer.name, KnownPlayer.server, KnownPlayer.region,
            KnownPlayer.class_name, KnownPlayer.spec,
        )
        .where(KnownPlayer.tenant_id == tenant_id)
        .order_by(KnownPlayer.last_seen_at.desc())
        .limit(_KNOWN_PLAYERS_SCAN)
    )
    # Profile rows first, so their class/spec wins for an identity both tables hold.
    people: dict[tuple[str, str, str], ResolvedCharacter] = {}
    for row in [*own, *known]:
        identity = (name_key(row[0]), name_key(row[1]), (row[2] or "").upper())
        if identity not in people:
            people[identity] = ResolvedCharacter(
                row[0], row[1], (row[2] or "").upper(), row[3], row[4], identity[0]
            )
    matches = [
        p for (k, server, _), p in people.items() if k == key and (not realm_key or server == realm_key)
    ]
    if matches:
        return _one("character", text, matches, lambda p: f"{p.name}-{p.server} ({p.region})")
    raise ResolutionError("character", text, "unknown", _close(key, [p.name for p in people.values()]))
