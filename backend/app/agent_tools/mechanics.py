"""Boss-mechanic lookup (feature 081, sc-571): specs/081-boss-mechanics/contracts/mechanics-tool.md.

Curated notes for the current raid tier live in ``backend/app/kb/mechanics/*.json``. They are read
once, at import, from that fixed directory and validated, so no argument ever names or opens a
file. Lookup is exact on normalised names, aliases and ability ids; the argument text is never
echoed back, only canonical names from the notes.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DATA_DIR = Path(__file__).resolve().parent.parent / "kb" / "mechanics"
MAX_ARG_CHARS = 100

_MISS = "Not in my mechanic guides."
_BAD_ABILITY = f"Pass the ability's name (at most {MAX_ARG_CHARS} characters)."
_BAD_ENCOUNTER = f"encounter must be a boss name of at most {MAX_ARG_CHARS} characters."
_APOSTROPHES = re.compile("['‘’ʼ`´′]")
_POSSESSIVE = re.compile(r"'s\b")
_SEPARATORS = re.compile(r"[\W_]+")
_DIFFICULTY_WORDS = frozenset({"lfr", "normal", "heroic", "mythic"})


class _Note(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Source(_Note):
    name: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://[^\s]+$")


class Ability(_Note):
    name: str = Field(min_length=1)
    ids: tuple[int, ...] = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    what_it_does: str = Field(min_length=1, max_length=400)
    what_to_do: str = Field(min_length=1, max_length=500)
    source: Source
    patch: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class Encounter(_Note):
    id: int
    name: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    abilities: tuple[Ability, ...]


class Zone(_Note):
    id: int
    name: str


class TierNotes(_Note):
    zone: Zone
    note: str = ""
    encounters: tuple[Encounter, ...]


def normalise(text: str) -> str:
    """Lookup key: NFKC, case-folded, any apostrophe style and a possessive 's dropped,
    punctuation and control characters as word breaks, a leading "the" dropped."""
    text = _APOSTROPHES.sub("'", unicodedata.normalize("NFKC", text).casefold())
    words = _SEPARATORS.sub(" ", _POSSESSIVE.sub("", text).replace("'", "")).split()
    return " ".join(words[1:] if words[:1] == ["the"] else words)


def _encounter_key(text: str) -> str:
    """``normalise`` with difficulty words dropped: "Ula'tek (Mythic)" is Ula'tek (BUG-002)."""
    return " ".join(w for w in normalise(text).split() if w not in _DIFFICULTY_WORDS)


def load_notes(data_dir: Path = DATA_DIR) -> tuple[Encounter, ...]:
    """Every tier file in ``data_dir``, validated (a bad file fails app start-up and the tests)."""
    return tuple(
        enc
        for path in sorted(data_dir.glob("*.json"))
        for enc in TierNotes.model_validate_json(path.read_bytes()).encounters
    )


def _keys(name: str, aliases: tuple[str, ...]) -> set[str]:
    return {normalise(n) for n in (name, *aliases)} - {""}


def _index(
    encounters: tuple[Encounter, ...],
) -> tuple[dict[str, Encounter], dict[str, list[tuple[Encounter, Ability]]]]:
    by_encounter = {key: enc for enc in encounters for key in _keys(enc.name, enc.aliases)}
    by_key: dict[str, list[tuple[Encounter, Ability]]] = {}
    for enc in encounters:
        for ab in enc.abilities:
            for key in _keys(ab.name, ab.aliases) | {str(i) for i in ab.ids}:
                by_key.setdefault(key, []).append((enc, ab))
    return by_encounter, by_key


ENCOUNTERS = load_notes()
_BY_ENCOUNTER, _BY_KEY = _index(ENCOUNTERS)
_UNKNOWN = Encounter(id=0, name="unknown", abilities=())  # a named boss the notes don't have


def _candidates(key: str) -> list[tuple[Encounter, Ability]]:
    """Notes whose name, alias or id is ``key``; else, with a boss's own name inside the text
    ("ula'tek heart"), that boss's notes matching the rest."""
    if key in _BY_KEY:
        return _BY_KEY[key]
    padded = f" {key} "
    found = []
    for enc_key, enc in _BY_ENCOUNTER.items():
        if f" {enc_key} " in padded:
            rest = normalise(padded.replace(f" {enc_key} ", " ", 1))
            found += [(e, a) for e, a in _BY_KEY.get(rest, []) if e is enc]
    return found


def _miss(found_under: list[Encounter], named: Encounter | None) -> dict:
    """A miss; ``found_under`` names (canonically) where the ability is, if anywhere."""
    result: dict = {"status": "success", "found": False, "message": _MISS}
    if found_under:
        if named is not None and named is not _UNKNOWN:
            result["message"] = f"Not in my mechanic guides for {named.name}."
        result["found_under"] = list(dict.fromkeys(e.name for e in found_under))
    return result


def _valid(value: object) -> bool:
    return isinstance(value, str) and len(value) <= MAX_ARG_CHARS


async def get_boss_mechanics(ability: str, encounter: str | None = None) -> dict:
    """Look up a current-tier raid boss mechanic in the curated guides: what it does and what to do.

    Pass the ability's name or ability id and, when known, the boss. Cite the hit's source and
    patch, then check the player in the log with its ability_ids. found false: say it is not in
    your guides, never invent the mechanic; found_under names the boss to ask with instead.
    """
    if not _valid(ability) or not normalise(ability):
        return {"status": "error", "error_message": _BAD_ABILITY}
    if encounter is not None and not _valid(encounter):
        return {"status": "error", "error_message": _BAD_ENCOUNTER}
    named = None
    if encounter is not None and _encounter_key(encounter):
        named = _BY_ENCOUNTER.get(_encounter_key(encounter), _UNKNOWN)
    candidates = _candidates(normalise(ability))
    if named is not None:
        hits = [c for c in candidates if c[0] is named]
    else:
        hits = candidates if len({id(e) for e, _ in candidates}) == 1 else []
    if not hits:
        return _miss([e for e, _ in candidates], named)
    enc, note = hits[0]
    return {
        "status": "success",
        "found": True,
        "encounter": enc.name,
        "ability": note.name,
        "ability_ids": list(note.ids),
        "what_it_does": note.what_it_does,
        "what_to_do": note.what_to_do,
        "source": {"name": note.source.name, "url": note.source.url},
        "patch": note.patch,
    }
