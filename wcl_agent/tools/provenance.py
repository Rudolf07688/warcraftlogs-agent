"""Provenance + completeness envelope for Warcraft Logs tool results (feature 009).

Every successful WCL tool result gains two **additive** keys so the model can say
where a number came from and whether the data behind it is complete (FR-020,
FR-022):

* ``provenance`` — the identifiers that scope the call (report, fight, encounter,
  difficulty, partition, metric, source, compare/timeframe) plus ``fetched_at``.
  Only the keys that apply are emitted.
* ``completeness`` — ``has_more`` (more pages / ``nextPageTimestamp``),
  ``truncated`` (the payload exceeded the size cap and is a preview),
  ``sample_size`` / ``sample_scope`` for leaderboard statistics.

Existing result keys are never changed; error results are returned untouched.
``_cap`` (``report_tools``) is left as-is — the helper only *detects* its
``_truncated`` marker.

Also home to :class:`PercentileContext` and :func:`flatten_report_rankings`,
the flattened view of ``report.rankings`` reused by the percentile tool (US3) and
the benchmark cohort (US2).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with second precision, e.g. ``2026-10-07T14:03:11Z``."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Provenance:
    """Identifiers that scope a WCL tool call. ``None`` keys are dropped on emit."""

    report_code: str | None = None
    fight_id: int | None = None
    encounter_id: int | None = None
    difficulty: int | None = None
    partition: int | None = None
    metric: str | None = None
    source_id: int | None = None
    compare: str | None = None
    timeframe: str | None = None
    fetched_at: str = field(default_factory=_now_iso)


@dataclass
class Completeness:
    """How complete the returned data is relative to what WCL holds."""

    has_more: bool = False
    truncated: bool = False
    sample_size: int | None = None
    sample_scope: str | None = None  # "full" | "top_of_leaderboard" | "band_clipped"


def was_truncated(result: dict[str, Any]) -> bool:
    """True when any top-level value is a ``_cap`` truncated preview."""
    return any(
        isinstance(value, dict) and value.get("_truncated") is True
        for value in result.values()
    )


def with_envelope(
    result: dict[str, Any],
    provenance: Provenance,
    completeness: Completeness | None = None,
) -> dict[str, Any]:
    """Attach ``provenance`` + ``completeness`` to a non-error tool result.

    Error results (``status == "error"``) are returned unchanged so existing
    error shapes and their consumers are unaffected. ``completeness.truncated``
    is forced to True whenever the result carries a ``_cap`` truncated preview,
    so the model can flag partial data instead of silently analysing a prefix.
    """
    if result.get("status") == "error":
        return result
    completeness = completeness or Completeness()
    if was_truncated(result):
        completeness.truncated = True
    result["provenance"] = {k: v for k, v in asdict(provenance).items() if v is not None}
    result["completeness"] = asdict(completeness)
    return result


# --- Percentile context (report.rankings flattened) ---------------------------

_ROLE_KEYS = (("tanks", "tank"), ("healers", "healer"), ("dps", "dps"))


@dataclass
class PercentileContext:
    """One ranked player in one fight, with every qualifier a percentile needs (FR-018)."""

    name: str | None
    server: str | None
    class_name: str | None
    spec: str | None
    role: str | None
    population: str  # "rankings" (best per character) | "parses" (all recent pulls)
    timeframe: str  # "historical" | "today"
    rank_percent: float | None
    bracket_percent: float | None
    bracket: int | None
    item_level: float | None
    total_parses: int | None
    partition: int | None
    metric: str
    encounter_id: int | None
    difficulty: int | None
    fight_id: int | None
    kill: bool | None
    duration_s: float | None
    amount: float | None


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _server_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("name")
    return value if isinstance(value, str) else None


def flatten_report_rankings(
    raw: dict[str, Any] | None,
    *,
    compare: str,
    timeframe: str,
    metric: str,
) -> list[PercentileContext]:
    """Walk the ``report.rankings`` JSON scalar into one row per ranked player.

    Shape (verified live, research R1): ``raw["data"][]`` → per fight ``fightID,
    partition, encounter{id}, difficulty, kill, duration`` →
    ``roles.{tanks,healers,dps}.characters[]`` → ``name, server, class, spec,
    rankPercent, bracketPercent, bracket, bracketData, totalParses, amount``.
    Every key is optional; missing values become ``None``.
    """
    rows: list[PercentileContext] = []
    fights = (raw or {}).get("data") or []
    population = "parses" if compare.lower() == "parses" else "rankings"
    tf = "today" if timeframe.lower() == "today" else "historical"
    for fight in fights:
        if not isinstance(fight, dict):
            continue
        encounter = fight.get("encounter") or {}
        duration_ms = _num(fight.get("duration"))
        roles = fight.get("roles") or {}
        for role_key, role in _ROLE_KEYS:
            characters = (roles.get(role_key) or {}).get("characters") or []
            for ch in characters:
                if not isinstance(ch, dict):
                    continue
                rows.append(
                    PercentileContext(
                        name=ch.get("name"),
                        server=_server_name(ch.get("server")),
                        class_name=ch.get("class"),
                        spec=ch.get("spec"),
                        role=role,
                        population=population,
                        timeframe=tf,
                        rank_percent=_num(ch.get("rankPercent")),
                        bracket_percent=_num(ch.get("bracketPercent")),
                        bracket=_int(ch.get("bracket")),
                        item_level=_num(ch.get("bracketData")),
                        total_parses=_int(ch.get("totalParses")),
                        partition=_int(fight.get("partition")),
                        metric=metric,
                        encounter_id=_int(encounter.get("id") if isinstance(encounter, dict) else None),
                        difficulty=_int(fight.get("difficulty")),
                        fight_id=_int(fight.get("fightID")),
                        kill=fight.get("kill"),
                        duration_s=None if duration_ms is None else round(duration_ms / 1000, 1),
                        amount=_num(ch.get("amount")),
                    )
                )
    return rows
