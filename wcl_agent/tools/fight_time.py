"""Fight-time helpers shared by the benchmark (US2) and cooldown (US4) tools.

Everything here works in **report-relative milliseconds** (the unit Warcraft Logs
uses for ``startTime``/``endTime``/event ``timestamp``) and returns seconds only
from :func:`eligible_seconds`.

* :func:`resolve_player` — turn a player name (or ``source_id``) into one actor
  of the fight, refusing ambiguous names (FR-006).
* :func:`dead_windows` / :func:`fetch_dead_windows` — time dead, from each death
  to the player's first cast after it (battle-res) or the fight end (research R5).
* :func:`intermission_windows` — phases flagged ``isIntermission``.
* :func:`eligible_seconds` — fight time minus the merged windows.

Eligible/alive time is deliberately **not** WCL's ``activeTime`` (time spent
casting — a performance measure, not an opportunity window).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .report_tools import _report_field
from ..client.aio import gather_settled, unwrap

Interval = tuple[float, float]


class PlayerResolutionError(Exception):
    """Carries the tool-shaped error dict for an unresolved or ambiguous player."""

    def __init__(self, result: dict[str, Any]):
        super().__init__(result.get("error_message", "player resolution failed"))
        self.result = result


@dataclass(frozen=True)
class ResolvedPlayer:
    source_id: int
    name: str
    server: str | None
    class_name: str | None


def _server_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("name")
    return value if isinstance(value, str) else None


def resolve_player(
    actors: list[dict[str, Any]],
    fight_player_ids: list[int] | None,
    player_name: str,
    source_id: int = 0,
) -> ResolvedPlayer:
    """Resolve one player of a fight from masterData actors + ``friendlyPlayers``.

    ``source_id > 0`` wins over ``player_name``. Otherwise the name must match
    exactly one actor present in the fight: zero matches → error naming the
    players present; several → ``AmbiguousPlayer`` error listing the candidates
    (data-model §4.3a). Raises :class:`PlayerResolutionError`.
    """
    present_ids = set(fight_player_ids) if fight_player_ids else None
    present = [
        a for a in actors
        if isinstance(a, dict) and (present_ids is None or a.get("id") in present_ids)
    ]

    def _resolved(actor: dict[str, Any]) -> ResolvedPlayer:
        return ResolvedPlayer(
            source_id=int(actor["id"]),
            name=str(actor.get("name")),
            server=_server_name(actor.get("server")),
            class_name=actor.get("subType"),
        )

    if source_id:
        for actor in present:
            if actor.get("id") == source_id:
                return _resolved(actor)
        raise PlayerResolutionError(
            {
                "status": "error",
                "error_message": f"source_id {source_id} is not a player in this fight.",
                "players_present": sorted(str(a.get("name")) for a in present),
            }
        )

    wanted = (player_name or "").strip().casefold()
    matches = [a for a in present if str(a.get("name", "")).casefold() == wanted]
    if not matches:
        raise PlayerResolutionError(
            {
                "status": "error",
                "error_message": f"No player named '{player_name}' in this fight.",
                "players_present": sorted(str(a.get("name")) for a in present),
            }
        )
    if len(matches) > 1:
        raise PlayerResolutionError(
            {
                "status": "error",
                "error_message": (
                    f"Player name '{player_name}' matches {len(matches)} actors in this "
                    "fight; pass source_id."
                ),
                "candidates": [
                    {
                        "source_id": a.get("id"),
                        "name": a.get("name"),
                        "server": _server_name(a.get("server")),
                        "class": a.get("subType"),
                    }
                    for a in matches
                ],
            }
        )
    return _resolved(matches[0])


# --- Interval maths ---------------------------------------------------------------


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping or touching ``(start, end)`` pairs; drop empty ones."""
    cleaned = sorted((float(s), float(e)) for s, e in intervals if e is not None and e > s)
    merged: list[Interval] = []
    for start, end in cleaned:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def dead_windows(
    death_ts: list[float],
    next_cast_ts: list[float | None],
    fight_end: float,
) -> list[Interval]:
    """One window per death: from the death to the next cast, else the fight end."""
    windows: list[Interval] = []
    for death, next_cast in zip(death_ts, next_cast_ts, strict=True):
        end = fight_end if next_cast is None else min(float(next_cast), fight_end)
        windows.append((float(death), end))
    return merge_intervals(windows)


def _dedupe_deaths(timestamps: list[float], tolerance_ms: float = 1000) -> list[float]:
    """Deaths tables repeat an entry per death event; collapse near-duplicates."""
    out: list[float] = []
    for ts in sorted(timestamps):
        if not out or ts - out[-1] > tolerance_ms:
            out.append(ts)
    return out


async def fetch_dead_windows(
    report_code: str,
    fight_id: int,
    source_id: int,
    fight_end: float,
) -> list[Interval]:
    """Deaths table → the player's death timestamps; one next-cast event per death.

    Costs 1 call + 1 per death (all through the cached client); the per-death calls run
    concurrently on the loop (PERF-002, feature 013). Raises on WCL errors so the calling tool can report them.
    """
    table = await _report_field(
        report_code,
        "table(dataType: Deaths, fightIDs: $fightIDs, sourceID: $sourceID)",
        ", $fightIDs: [Int], $sourceID: Int",
        {"fightIDs": [fight_id], "sourceID": source_id},
        "table",
    )
    entries = ((table or {}).get("data") or {}).get("entries") or []
    deaths = _dedupe_deaths(
        [
            float(e["timestamp"])
            for e in entries
            if isinstance(e, dict) and e.get("timestamp") is not None
            and (e.get("id") in (None, source_id))
        ]
    )
    async def next_cast(death: float) -> float | None:
        events = await _report_field(
            report_code,
            "events(dataType: Casts, fightIDs: $fightIDs, sourceID: $sourceID, "
            "startTime: $startTime, limit: 1) { data nextPageTimestamp }",
            ", $fightIDs: [Int], $sourceID: Int, $startTime: Float",
            {"fightIDs": [fight_id], "sourceID": source_id, "startTime": death + 1},
            "events",
        )
        data = (events or {}).get("data") or []
        first = data[0] if data and isinstance(data[0], dict) else None
        ts = first.get("timestamp") if first else None
        return float(ts) if ts is not None else None

    results = await gather_settled(*(next_cast(d) for d in deaths))
    next_casts = [unwrap(r) for r in results]  # first failure (in death order) is raised
    return dead_windows(deaths, next_casts, fight_end)


def intermission_windows(
    fight_start: float,
    fight_end: float,
    phase_transitions: list[dict[str, Any]] | None,
    intermission_phase_ids: set[int],
) -> list[Interval]:
    """Windows from each intermission transition to the next transition / fight end."""
    transitions = sorted(
        (t for t in (phase_transitions or []) if isinstance(t, dict) and t.get("startTime") is not None),
        key=lambda t: float(t["startTime"]),
    )
    windows: list[Interval] = []
    for i, t in enumerate(transitions):
        if t.get("id") not in intermission_phase_ids:
            continue
        start = max(float(t["startTime"]), fight_start)
        end = float(transitions[i + 1]["startTime"]) if i + 1 < len(transitions) else fight_end
        windows.append((start, min(end, fight_end)))
    return merge_intervals(windows)


def eligible_seconds(fight_start: float, fight_end: float, *window_lists: list[Interval]) -> float:
    """Fight length minus the merged excluded windows, in seconds (never below 0)."""
    clipped = [
        (max(s, fight_start), min(e, fight_end))
        for windows in window_lists
        for s, e in windows
    ]
    excluded = sum(e - s for s, e in merge_intervals(clipped))
    return max(0.0, (fight_end - fight_start - excluded) / 1000)


def windows_seconds(windows: list[Interval]) -> float:
    return round(sum(e - s for s, e in merge_intervals(windows)) / 1000, 1)
