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
from ..db.models import TrackedRaid
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
    graphs = [
        {
            "data_type": g.data_type,
            "report_code": g.report_code,
            "graph_json": g.graph_json,
            "fight_id": g.fight_id,
            "source_id": g.source_id,
        }
        for g in await repo.list_captured_graphs(session, conv_id)
    ]

    # Prefer a tracked-raid label for the header when one points at this chat.
    raid = (
        await session.execute(
            select(TrackedRaid).where(TrackedRaid.last_conversation_id == conv_id)
        )
    ).scalars().first()
    title = raid.label if raid else (conv.title or "WCL Report")

    try:
        pdf_bytes = await asyncio.to_thread(
            render_report_pdf,
            title=title,
            generated_at=datetime.now(timezone.utc),
            messages=messages,
            graphs=graphs,
        )
    except Exception:  # noqa: BLE001 - never present a partial file as complete
        logger.exception("PDF generation failed for conversation %s", conv_id)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")

    short_id = str(conv_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="wcl-report-{short_id}.pdf"'},
    )
