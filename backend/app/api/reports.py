"""REST: download a conversation as a PDF report with graphs (US5)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.tools.benchmark import report_link

from ..auth.dependencies import get_tenant_db, require_session
from ..db import repository as repo
from ..db.models import Message, TrackedRaid
from ..schemas import ChartSpec
from ..services import charts, report_synthesis
from ..services.pdf_report import ReportDocument, ReportFigure, render_report_pdf
from ..tenancy.context import RequestIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["reports"])

# Render limits (QA SEC-003/PERF-003, PERF-010..012). Chart drawing and PDF layout are
# CPU-bound and hold the GIL, so parallel renders only slow each other down (4 renders:
# 1.8 s one at a time, 2.7 s two at a time). One dedicated thread runs them in turn; the
# queue lives in its work queue, not in parked threads of the default executor that the
# chat path also needs. Work that overruns its wait keeps the thread until it really ends.
_RENDER_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-render")
_MAX_FIGURES = 20
_CHARTS_TIMEOUT_S = 60.0
_RENDER_TIMEOUT_S = 90.0


@dataclass(frozen=True)
class GraphSource:
    """A captured WCL graph as plain data, safe to hand to a worker thread."""

    data_type: str
    report_code: str
    fight_id: int
    graph_json: Any


@dataclass(frozen=True)
class ChartSource:
    """An agent chart's stored spec as plain data, safe to hand to a worker thread."""

    spec_json: Any


def _sources(graphs, artifacts) -> tuple[tuple[GraphSource, ...], tuple[ChartSource, ...]]:
    return (
        tuple(GraphSource(g.data_type, g.report_code, g.fight_id, g.graph_json) for g in graphs),
        tuple(ChartSource(a.spec_json) for a in artifacts),
    )


async def _on_render_pool(fn, arg, *, timeout: float):
    """Run CPU-bound report work on the render thread, waiting at most ``timeout``.

    Queued work that hasn't started when the wait runs out is cancelled; work already
    running can't be killed and keeps the thread until it ends (the input caps bound it).
    """
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(loop.run_in_executor(_RENDER_POOL, fn, arg), timeout)


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
    graphs, charts_in = _sources(
        await repo.list_captured_graphs(session, conv_id, tenant_id=tid),
        await repo.list_artifacts(session, conv_id, tenant_id=tid),
    )

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
        charts_in=charts_in,
        ctx=str(conv_id),
        scope="conversation",
    )
    short_id = str(conv_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="wcl-report-{short_id}.pdf"'},
    )


async def _figures(
    graphs: tuple[GraphSource, ...], charts_in: tuple[ChartSource, ...]
) -> tuple[ReportFigure, ...]:
    """Charts for the report: captured WCL graphs first, then the agent's charts (FR-012).

    Each chart is its own job on the render thread (FR-022), so a waiting render gets in
    after at most one chart. A chart that fails to validate or draw, or misses the chart
    step's deadline, becomes ``svg=None`` ("Chart unavailable") instead of failing the
    whole report (FR-016).
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _CHARTS_TIMEOUT_S

    async def draw(fn, arg, what: str) -> bytes | None:
        remaining = deadline - loop.time()
        if remaining <= 0:
            logger.warning("chart step out of time; %s left unavailable", what)
            return None
        try:
            return await _on_render_pool(fn, arg, timeout=remaining)
        except Exception:  # noqa: BLE001 - one bad chart must not sink the report
            logger.exception("chart render failed for %s", what)
            return None

    out: list[ReportFigure] = []
    for g in graphs:
        title = g.data_type + (f" — {g.report_code}" if g.report_code else "")
        svg = await draw(charts.graph_to_svg, g.graph_json, title)
        url = report_link(g.report_code, g.fight_id or None) if g.report_code else ""
        out.append(ReportFigure(title=title, svg=svg, source_url=url))
    for a in charts_in:
        spec_json = a.spec_json or {}
        try:
            spec = ChartSpec.model_validate(spec_json)
        except Exception:  # noqa: BLE001 - a malformed spec must not sink the report
            logger.exception("chart spec invalid")
            title = spec_json.get("title") if isinstance(spec_json, dict) else None
            out.append(ReportFigure(title=str(title or "Chart"), svg=None))
            continue
        svg = await draw(charts.chart_spec_to_svg, spec, spec.title)
        out.append(ReportFigure(title=spec.title, svg=svg, source_url=spec.source_url))
    return tuple(out)


async def _render(doc: ReportDocument, *, ctx: str) -> bytes:
    try:
        return await _on_render_pool(render_report_pdf, doc, timeout=_RENDER_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - never present a partial file as complete
        logger.exception("PDF generation failed for %s", ctx)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")


async def _synthesize_and_render(
    *,
    title: str,
    messages: list[dict],
    graphs: tuple[GraphSource, ...],
    charts_in: tuple[ChartSource, ...],
    ctx: str,
    scope: str,
    question: str | None = None,
    partial: bool = False,
) -> bytes:
    """Shared findings pipeline for both report scopes (US2/US3, FR-016).

    Synthesizes the in-scope messages into a findings document and renders that as the
    PDF body (charts attached unchanged). Fail-closed (FR-018): a synthesis error,
    timeout, or empty output yields a clean 500 and no partial file.
    """
    # Cap the charts so one report can't hold the render thread unboundedly (QA PERF-012).
    omitted = max(0, len(graphs) + len(charts_in) - _MAX_FIGURES)
    graphs = graphs[:_MAX_FIGURES]
    charts_in = charts_in[: _MAX_FIGURES - len(graphs)]
    # Charts are drawn on the render thread while the findings model call runs (FR-022).
    findings_md, figures = await asyncio.gather(
        report_synthesis.synthesize_findings(messages, scope=scope, question=question),
        _figures(graphs, charts_in),
        return_exceptions=True,
    )
    if isinstance(findings_md, BaseException):  # synthesis failure/timeout → fail closed
        logger.error("findings synthesis failed for %s", ctx, exc_info=findings_md)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")
    if isinstance(figures, BaseException):
        logger.error("chart rendering failed for %s", ctx, exc_info=figures)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")
    if not findings_md.strip():
        # Empty model output is a malfunction, not a valid "no findings" doc (FR-018);
        # the prompt makes the model emit its own no-findings document when apt (FR-017).
        logger.error("findings synthesis produced empty output for %s", ctx)
        raise HTTPException(status_code=500, detail="pdf_generation_failed")
    doc = ReportDocument(
        title=title,
        scope=scope,
        generated_at=datetime.now(timezone.utc),
        body_markdown=findings_md,
        question=question,
        partial=partial,
        figures=figures,
        figures_omitted=omitted,
    )
    return await _render(doc, ctx=ctx)


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

    graphs, charts_in = _sources(
        [g for g in await repo.list_captured_graphs(session, conv_id, tenant_id=tid) if g.message_seq == seq],
        [a for a in await repo.list_artifacts(session, conv_id, tenant_id=tid) if a.message_seq == seq],
    )

    conv = await repo.get_conversation(session, conv_id, tenant_id=tid)
    title = (conv.title if conv else None) or "WCL Report"

    pdf_bytes = await _synthesize_and_render(
        title=title,
        messages=messages,
        graphs=graphs,
        charts_in=charts_in,
        ctx=str(message_id),
        scope="message",
        question=question.content if question is not None else None,
        partial=msg.status == "partial",
    )
    short_id = str(message_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="wcl-message-{short_id}.pdf"'},
    )
