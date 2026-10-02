"""REST: download a conversation as a PDF report with graphs (US5)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repository as repo
from ..db.models import Message, TrackedRaid
from ..db.session import get_session
from ..services.pdf_report import render_report_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["reports"])


@router.get("/{conv_id}/report.pdf")
async def download_report(
    conv_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Response:
    conv = await repo.get_conversation(session, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="not_found")

    messages = [
        {"role": m.role, "content": m.content, "status": m.status}
        for m in await repo.list_messages(session, conv_id)
    ]
    graphs = _graph_dicts(await repo.list_captured_graphs(session, conv_id))
    artifacts = _artifact_dicts(await repo.list_artifacts(session, conv_id))

    # Prefer a tracked-raid label for the header when one points at this chat.
    raid = (
        await session.execute(
            select(TrackedRaid).where(TrackedRaid.last_conversation_id == conv_id)
        )
    ).scalars().first()
    title = raid.label if raid else (conv.title or "WCL Report")

    pdf_bytes = await _render(
        title=title, messages=messages, graphs=graphs, artifacts=artifacts, ctx=str(conv_id)
    )
    short_id = str(conv_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="wcl-report-{short_id}.pdf"'},
    )


def _graph_dicts(graphs) -> list[dict]:
    return [
        {
            "data_type": g.data_type,
            "report_code": g.report_code,
            "graph_json": g.graph_json,
            "fight_id": g.fight_id,
            "source_id": g.source_id,
        }
        for g in graphs
    ]


def _artifact_dicts(artifacts) -> list[dict]:
    return [{"spec_json": a.spec_json} for a in artifacts]


async def _render(*, title, messages, graphs, artifacts, ctx: str) -> bytes:
    try:
        return await asyncio.to_thread(
            render_report_pdf,
            title=title,
            generated_at=datetime.now(timezone.utc),
            messages=messages,
            graphs=graphs,
            artifacts=artifacts,
        )
    except Exception:  # noqa: BLE001 - never present a partial file as complete
        logger.exception("PDF generation failed for %s", ctx)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")


@router.get("/{conv_id}/messages/{message_id}/report.pdf")
async def download_message_report(
    conv_id: uuid.UUID,
    message_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Render a PDF scoped to one agent reply + its originating question + its charts.

    Excludes all other messages (FR-023); captures are matched by ``message_seq``.
    """
    msg = await session.get(Message, message_id)
    if msg is None or msg.conversation_id != conv_id or msg.role != "agent":
        raise HTTPException(status_code=404, detail="not_found")
    seq = msg.seq

    all_msgs = await repo.list_messages(session, conv_id)
    # Nearest preceding user message is the question that prompted this reply.
    preceding = [m for m in all_msgs if m.seq < seq and m.role == "user"]
    question = preceding[-1] if preceding else None

    messages: list[dict] = []
    if question is not None:
        messages.append(
            {"role": "user", "content": question.content, "status": question.status}
        )
    messages.append({"role": "agent", "content": msg.content, "status": msg.status})

    graphs = _graph_dicts(
        [g for g in await repo.list_captured_graphs(session, conv_id) if g.message_seq == seq]
    )
    artifacts = _artifact_dicts(
        [a for a in await repo.list_artifacts(session, conv_id) if a.message_seq == seq]
    )

    conv = await repo.get_conversation(session, conv_id)
    title = (conv.title if conv else None) or "WCL Report"

    pdf_bytes = await _render(
        title=title, messages=messages, graphs=graphs, artifacts=artifacts, ctx=str(message_id)
    )
    short_id = str(message_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="wcl-message-{short_id}.pdf"'},
    )
