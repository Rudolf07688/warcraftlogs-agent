"""REST: conversation lifecycle (list / create / get / delete)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repository as repo
from ..db.session import get_session
from ..model_state import is_valid_model
from ..schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationOut,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    session: AsyncSession = Depends(get_session),
) -> ConversationListResponse:
    convs = await repo.list_conversations(session)
    return ConversationListResponse(
        conversations=[ConversationOut.model_validate(c) for c in convs]
    )


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    if not is_valid_model(request.app, body.model):
        raise HTTPException(status_code=400, detail="invalid_model")
    conv = await repo.create_conversation(session, model=body.model, title=body.title)
    return ConversationOut.model_validate(conv)


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ConversationDetail:
    conv = await repo.get_conversation(session, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="not_found")
    return ConversationDetail.model_validate(conv)


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    deleted = await repo.delete_conversation(session, conv_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")
