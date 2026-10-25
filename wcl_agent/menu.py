"""Interactive terminal menu for choosing a raid encounter + difficulty.

One :data:`~wcl_agent.client.queries.MENU_DISCOVERY` call fetches every zone with its
encounters, difficulties, and partitions; the user then drills down via numbered
prompts. The returned context dict is stored in the ADK session state so the
agent's tools know what to analyze.
"""

from __future__ import annotations

from typing import Any

from .cache.cache import CacheFamily, get_or_load, keys
from .cache.cache_models import WorldZones
from .client.queries import MENU_DISCOVERY
from .client import wcl_client


async def load_world_zones() -> list[dict[str, Any]]:
    """Every zone with its encounters, difficulties and partitions (``world_zones``, feature 014).

    The one way code reads the zone list: the patch preamble runs on every chat turn, so this
    is cached for everyone (1h by default).
    """

    async def load() -> WorldZones:
        data = await wcl_client.get_async_client().query(MENU_DISCOVERY)
        return WorldZones(zones=((data.get("data") or {}).get("worldData") or {}).get("zones") or [])

    zones = await get_or_load(CacheFamily.WORLD_ZONES, keys.WORLD_ZONES, WorldZones, load)
    return zones.zones if zones is not None else []


def _prompt_choice(title: str, options: list[str]) -> int:
    """Print a numbered menu and return the chosen 0-based index."""
    print(f"\n{title}")
    for i, label in enumerate(options, start=1):
        print(f"  {i}. {label}")
    while True:
        raw = input("Select a number: ").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        print(f"  Please enter a number between 1 and {len(options)}.")


def _default_partition(zone: dict[str, Any]) -> int | None:
    """Return the id of the zone's default partition (the current season)."""
    partitions = zone.get("partitions") or []
    for part in partitions:
        if part.get("default"):
            return part["id"]
    return partitions[-1]["id"] if partitions else None


async def select_encounter() -> dict[str, Any]:
    """Run the interactive selection and return the chosen encounter context.

    Returns a dict with keys: ``zoneID``, ``zoneName``, ``encounterID``,
    ``encounterName``, ``difficultyID``, ``difficultyName``, ``partition``.
    """
    print("Fetching Warcraft Logs zones...")
    zones = await load_world_zones()

    # Prefer current (non-frozen) raids, but keep a fallback so selection never
    # ends up empty.
    active = [z for z in zones if not z.get("frozen") and z.get("encounters")]
    choices = active or [z for z in zones if z.get("encounters")]
    # Newest zones have the highest ids; show those first.
    choices.sort(key=lambda z: z["id"], reverse=True)

    zone_labels = [
        f"{z['name']}  ({(z.get('expansion') or {}).get('name', '?')})" for z in choices
    ]
    zone = choices[_prompt_choice("Choose a raid zone:", zone_labels)]

    encounters = zone["encounters"]
    enc = encounters[
        _prompt_choice(
            f"Choose an encounter in {zone['name']}:",
            [e["name"] for e in encounters],
        )
    ]

    difficulties = zone.get("difficulties") or []
    if difficulties:
        diff = difficulties[
            _prompt_choice("Choose a difficulty:", [d["name"] for d in difficulties])
        ]
    else:
        # Flexible/undifferentiated zone; fall back to Heroic (4).
        diff = {"id": 4, "name": "Heroic"}

    context = {
        "zoneID": zone["id"],
        "zoneName": zone["name"],
        "encounterID": enc["id"],
        "encounterName": enc["name"],
        "difficultyID": diff["id"],
        "difficultyName": diff["name"],
        "partition": _default_partition(zone),
    }
    print(
        f"\nSelected: {context['zoneName']} > {context['encounterName']} > "
        f"{context['difficultyName']}\n"
    )
    return context
