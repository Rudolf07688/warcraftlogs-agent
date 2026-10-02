"""Artifact capture (feature 005 / US2).

Recognizes a successful ``create_chart`` tool result on the agent-runner backbone
and validates its payload into a ``ChartSpec``. The WebSocket layer then persists
the spec (``repo.add_artifact``), derives the Plotly figure (``services.charts``),
and emits an ``artifact`` frame — mirroring how graphs/raids are captured.
"""

from __future__ import annotations

from pydantic import ValidationError

from ..schemas import ChartSpec

CHART_TOOL_NAME = "create_chart"


def capture_artifact_from_tool(name: str, ok: bool, result: dict) -> ChartSpec | None:
    """Return a validated ChartSpec if this record is a successful create_chart call."""
    if not ok or name != CHART_TOOL_NAME:
        return None
    chart = (result or {}).get("chart")
    if not isinstance(chart, dict):
        return None
    try:
        return ChartSpec.model_validate(chart)
    except ValidationError:
        return None
