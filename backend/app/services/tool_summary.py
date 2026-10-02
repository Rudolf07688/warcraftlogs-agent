"""Short, human-readable summaries of a tool result for resolved spell chips (US6).

The WebSocket layer sends one (≤140 char) line per ``tool_end`` so the UI can show
what a tool actually did (e.g. "DamageDone — 23 abilities, 1 player") instead of a
bare tool name. Pure and defensive: unknown shapes degrade to a generic summary or
``None`` (the client then just shows the verb), and errors surface their message.
"""

from __future__ import annotations

from typing import Any

_MAX = 140


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX else text[: _MAX - 1].rstrip() + "…"


def _count(result: dict, *keys: str) -> int | None:
    for key in keys:
        val = result.get(key)
        if isinstance(val, list):
            return len(val)
        if isinstance(val, dict):
            return len(val)
    return None


def summarize_tool_result(name: str, ok: bool, result: dict[str, Any] | None) -> str | None:
    """Return a short human-readable summary of a tool result, or ``None``.

    On failure, prefer the tool's own error message so the fizzled card can show why.
    """
    result = result if isinstance(result, dict) else {}
    if not ok:
        msg = result.get("error_message") or result.get("error")
        return _clip(str(msg)) if msg else "failed"

    if name == "get_report_fights":
        fights = result.get("fights")
        n_fights = len(fights) if isinstance(fights, list) else 0
        bosses = {
            f.get("encounterID")
            for f in (fights or [])
            if isinstance(f, dict) and isinstance(f.get("encounterID"), int) and f.get("encounterID")
        }
        zone = result.get("zone")
        zone_name = zone.get("name") if isinstance(zone, dict) else None
        head = f"{n_fights} fights, {len(bosses)} bosses"
        return _clip(f"{head} — {zone_name}" if zone_name else head)

    if name in ("get_report_table", "get_report_graph", "get_report_events"):
        data_type = result.get("data_type") or (result.get("args") or {}).get("data_type")
        n = _count(result, "entries", "abilities", "data", "series", "events", "rows")
        parts = [str(data_type)] if data_type else []
        if n is not None:
            parts.append(f"{n} rows")
        return _clip(" — ".join(parts)) if parts else "ok"

    if name in ("get_rankings_distribution", "compare_specs", "get_report_rankings"):
        n = _count(result, "rankings", "specs", "distribution", "data")
        return _clip(f"{n} ranked entries") if n is not None else "ok"

    if name == "check_rate_limit":
        pts = result.get("points_spent_this_hour") or result.get("limit_per_hour")
        return _clip(f"rate limit: {pts}") if pts is not None else "ok"

    # Generic fallback: a short confirmation (title if any), else nothing.
    title = result.get("title") or result.get("name")
    return _clip(str(title)) if isinstance(title, str) and title else None
