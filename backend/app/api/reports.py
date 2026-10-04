"""REST: download a conversation as a PDF report with graphs (US5)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_tenant_db, require_session
from ..db import repository as repo
from ..db.models import Message, TrackedRaid
from ..services import report_synthesis
from ..services.pdf_report import render_report_pdf
from ..tenancy.context import RequestIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["reports"])


@router.get("/{conv_id}/report.pdf")
async def download_report(
    conv_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_session),
    session: AsyncSession = Depends(get_tenant_db),
) -> Response:
    tid = identity.tenant_id
    conv = await repo.get_conversation(session, conv_id, tenant_id=tid)
    if conv is None:
        raise HTTPException(status_code=404, detail="not_found")

    messages = [
        {"role": m.role, "content": m.content, "status": m.status}
        for m in await repo.list_messages(session, conv_id, tenant_id=tid)
    ]
    graphs = _graph_dicts(await repo.list_captured_graphs(session, conv_id, tenant_id=tid))
    artifacts = _artifact_dicts(await repo.list_artifacts(session, conv_id, tenant_id=tid))

    # Prefer a tracked-raid label for the header when one points at this chat.
    raid = (
        await session.execute(
            select(TrackedRaid).where(
                TrackedRaid.last_conversation_id == conv_id, TrackedRaid.tenant_id == tid
            )
        )
    ).scalars().first()
    title = raid.label if raid else (conv.title or "WCL Report")

    pdf_bytes = await _synthesize_and_render(
        title=title,
        messages=messages,
        graphs=graphs,
        artifacts=artifacts,
        ctx=str(conv_id),
        scope="conversation",
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


async def _synthesize_and_render(
    *,
    title: str,
    messages: list[dict],
    graphs: list[dict],
    artifacts: list[dict],
    ctx: str,
    scope: str,
    question: str | None = None,
) -> bytes:
    """Shared findings pipeline for both report scopes (US2/US3, FR-016).

    Synthesizes the in-scope messages into a findings document and renders that as the
    single-message PDF body (charts/artifacts attached unchanged). Fail-closed (FR-018):
    a synthesis error, timeout, or empty output yields a clean 500 and no partial file.
    """
    try:
        findings_md = await report_synthesis.synthesize_findings(
            messages, scope=scope, question=question
        )
    except Exception:  # noqa: BLE001 - synthesis failure/timeout → fail closed
        logger.exception("findings synthesis failed for %s", ctx)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")
    if not findings_md.strip():
        # Empty model output is a malfunction, not a valid "no findings" doc (FR-018);
        # the prompt makes the model emit its own no-findings document when apt (FR-017).
        logger.error("findings synthesis produced empty output for %s", ctx)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")
    synthetic = [{"role": "agent", "content": findings_md, "status": "complete"}]
    return await _render(
        title=title, messages=synthetic, graphs=graphs, artifacts=artifacts, ctx=ctx
    )


@router.get("/{conv_id}/messages/{message_id}/report.pdf")
async def download_message_report(
    conv_id: uuid.UUID,
    message_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_session),
    session: AsyncSession = Depends(get_tenant_db),
) -> Response:
    """Render a PDF scoped to one agent reply + its originating question + its charts.

    Excludes all other messages (FR-023); captures are matched by ``message_seq``.
    """
    tid = identity.tenant_id
    msg = (
        await session.execute(
            select(Message).where(Message.id == message_id, Message.tenant_id == tid)
        )
    ).scalar_one_or_none()
    if msg is None or msg.conversation_id != conv_id or msg.role != "agent":
        raise HTTPException(status_code=404, detail="not_found")
    seq = msg.seq

    all_msgs = await repo.list_messages(session, conv_id, tenant_id=tid)
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
        [g for g in await repo.list_captured_graphs(session, conv_id, tenant_id=tid) if g.message_seq == seq]
    )
    artifacts = _artifact_dicts(
        [a for a in await repo.list_artifacts(session, conv_id, tenant_id=tid) if a.message_seq == seq]
    )

    conv = await repo.get_conversation(session, conv_id, tenant_id=tid)
    title = (conv.title if conv else None) or "WCL Report"

    pdf_bytes = await _synthesize_and_render(
        title=title,
        messages=messages,
        graphs=graphs,
        artifacts=artifacts,
        ctx=str(message_id),
        scope="message",
        question=question.content if question is not None else None,
    )
    short_id = str(message_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="wcl-message-{short_id}.pdf"'},
    )
