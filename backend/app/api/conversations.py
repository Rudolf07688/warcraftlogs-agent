"""REST: conversation lifecycle (list / create / get / delete) — tenant-scoped (US3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_tenant_db, require_csrf, require_session
from ..db import repository as repo
from ..model_state import is_valid_model
from ..schemas import (
    ArtifactOut,
    ChartSpec,
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationOut,
)
from ..services.charts import chart_spec_to_plotly
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_tenant_db),
) -> ConversationListResponse:
    convs = await repo.list_conversations(db, tenant_id=identity.tenant_id)
    return ConversationListResponse(
        conversations=[ConversationOut.model_validate(c) for c in convs]
    )


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    request: Request,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> ConversationOut:
    if not is_valid_model(request.app, body.model):
        raise HTTPException(status_code=400, detail="invalid_model")
    conv = await repo.create_conversation(
        db, model=body.model, title=body.title, tenant_id=identity.tenant_id
    )
    return ConversationOut.model_validate(conv)


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_tenant_db),
) -> ConversationDetail:
    conv = await repo.get_conversation(db, conv_id, tenant_id=identity.tenant_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="not_found")
    detail = ConversationDetail.model_validate(conv)
    # US2: rebuild each persisted chart's Plotly figure from its stored spec (FR-011).
    artifacts = await repo.list_artifacts(db, conv_id, tenant_id=identity.tenant_id)
    detail.artifacts = [
        ArtifactOut(
            id=a.id,
            message_seq=a.message_seq,
            kind=a.kind,
            title=a.title,
            figure=chart_spec_to_plotly(ChartSpec.model_validate(a.spec_json)),
        )
        for a in artifacts
    ]
    return detail


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> None:
    deleted = await repo.delete_conversation(db, conv_id, tenant_id=identity.tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")
