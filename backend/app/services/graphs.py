"""Graph capture (US5): persist graph JSON the agent fetched, for PDF rendering.

Fed by the agent-runner backbone (see agent_runner.stream_response). When
``get_report_graph`` returns successfully during a turn, its ``graph`` payload is
stored against the conversation so the PDF export can render it later — no need to
re-call the tool (which would spend WCL rate budget and might miss the exact
filters used).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repository as repo
from ..db.models import CapturedGraph

GRAPH_TOOL_NAME = "get_report_graph"


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def capture_graph_from_tool(
    session: AsyncSession,
    *,
    name: str,
    ok: bool,
    args: dict,
    result: dict,
    conversation_id: uuid.UUID,
    message_seq: int | None = None,
) -> CapturedGraph | None:
    """Store a captured graph if this record is a successful get_report_graph call."""
    if not ok or name != GRAPH_TOOL_NAME:
        return None
    graph = (result or {}).get("graph")
    report_code = (args or {}).get("report_code")
    if not isinstance(graph, dict) or not isinstance(report_code, str) or not report_code:
        return None
    # Skip the tool's "too large" placeholder — nothing to chart from it.
    if graph.get("_truncated"):
        return None
    data_type = (args or {}).get("data_type") or (result or {}).get("data_type") or "Unknown"
    return await repo.add_captured_graph(
        session,
        conversation_id=conversation_id,
        report_code=report_code,
        data_type=str(data_type),
        graph_json=graph,
        fight_id=_as_int((args or {}).get("fight_id")),
        source_id=_as_int((args or {}).get("source_id")),
        message_seq=message_seq,
    )
