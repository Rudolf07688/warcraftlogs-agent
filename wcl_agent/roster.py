"""The live class/spec roster from Warcraft Logs game data (feature 015, research R12).

``load_roster()`` reads ``gameData.classes`` through the shared cache (24 h) and keeps the
result as the process snapshot; ``roster_snapshot()`` serves sync call sites (request
validation, role inference, tool argument checks). Any failure falls back to the static
``constants.CLASS_SPECS`` map, so a new spec (e.g. Devourer) appears as soon as WCL lists
it and the app still works offline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from . import wcl_client
from .cache import CacheFamily, get_or_load, keys
from .cache_models import GameClass, GameClasses, GameSpec
from .constants import _HEALER_SPECS, _TANK_SPECS, CLASS_SPECS
from .queries import GAME_CLASSES

logger = logging.getLogger(__name__)

RosterSource = Literal["game_data", "fallback"]


@dataclass(frozen=True)
class RosterSpec:
    class_name: str  # WCL filter value, e.g. "DemonHunter"
    class_display: str  # e.g. "Demon Hunter"
    spec: str  # WCL filter value, e.g. "Devourer"
    spec_display: str  # e.g. "Beast Mastery"
    role: str  # tank | healer | dps


@dataclass(frozen=True)
class Roster:
    specs: tuple[RosterSpec, ...]
    source: RosterSource
    _by_class: dict[str, list[RosterSpec]] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        for s in self.specs:
            self._by_class.setdefault(s.class_name, []).append(s)

    def classes(self) -> list[str]:
        return list(self._by_class)

    def class_display(self, class_name: str) -> str:
        specs = self._by_class.get(class_name)
        return specs[0].class_display if specs else class_name

    def specs_for(self, class_name: str) -> list[str]:
        return [s.spec for s in self._by_class.get(class_name, [])]

    def has(self, class_name: str, spec: str) -> bool:
        return spec in self.specs_for(class_name)

    def get(self, class_name: str, spec: str) -> RosterSpec | None:
        return next((s for s in self._by_class.get(class_name, []) if s.spec == spec), None)


def _role(spec: str) -> str:
    return "tank" if spec in _TANK_SPECS else "healer" if spec in _HEALER_SPECS else "dps"


def _spaced(value: str) -> str:
    """``BeastMastery`` → ``Beast Mastery`` (display name for the static fallback)."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)


def roster_from_game_classes(data: GameClasses) -> Roster:
    """Map game data to roster entries: ``slug`` is the filter value, ``name`` the label."""
    specs = [
        RosterSpec(c.slug, c.name, s.slug, s.name, _role(s.slug))
        for c in data.classes
        for s in c.specs
        if c.slug and s.slug
    ]
    return Roster(tuple(specs), "game_data")


def fallback_roster() -> Roster:
    specs = [
        RosterSpec(cls, str(info["display"]), spec, _spaced(spec), _role(spec))
        for cls, info in CLASS_SPECS.items()
        for spec in info["specs"]  # type: ignore[attr-defined]
    ]
    return Roster(tuple(specs), "fallback")


_current: Roster | None = None


def roster_snapshot() -> Roster:
    """The last loaded roster, or the static fallback before the first load (sync)."""
    return _current or fallback_roster()


async def _load_game_classes() -> GameClasses | None:
    data = await wcl_client.get_async_client().query(GAME_CLASSES)
    classes = ((data.get("data") or {}).get("gameData") or {}).get("classes") or []
    parsed = [
        GameClass(
            id=c.get("id"),
            name=c["name"],
            slug=c["slug"],
            specs=[GameSpec(id=s.get("id"), name=s["name"], slug=s["slug"]) for s in c.get("specs") or []],
        )
        for c in classes
        if c.get("slug") and c.get("name")
    ]
    return GameClasses(classes=parsed) if parsed else None


async def load_roster() -> Roster:
    """Load the live roster (cached) and make it the process snapshot; never raises."""
    global _current
    try:
        data = await get_or_load(CacheFamily.GAME_CLASSES, keys.GAME_CLASSES, GameClasses, _load_game_classes)
    except Exception as exc:  # noqa: BLE001 - the static map keeps the app working
        logger.warning("game-data roster unavailable, using the static fallback: %s", exc)
        data = None
    roster = roster_from_game_classes(data) if data is not None and data.classes else fallback_roster()
    _current = roster
    return roster


def role_for(spec: str | None) -> str | None:
    """Role for a spec (delegates to ``constants.role_for_spec``, which knows the roster)."""
    from .constants import role_for_spec

    return role_for_spec(spec)


def specs_for(class_name: str) -> list[str]:
    return roster_snapshot().specs_for(class_name)


def _loose(value: str) -> str:
    return (value or "").replace(" ", "").replace("'", "").replace("-", "").casefold()


def resolve_spec(class_name: str, spec: str) -> RosterSpec | None:
    """Match a loosely written class + spec ("demon hunter" / "devourer") to the roster."""
    want_class, want_spec = _loose(class_name), _loose(spec)
    for entry in roster_snapshot().specs:
        if want_class in (_loose(entry.class_name), _loose(entry.class_display)):
            if want_spec in (_loose(entry.spec), _loose(entry.spec_display)):
                return entry
    return None


def _reset_for_tests() -> None:
    global _current
    _current = None
