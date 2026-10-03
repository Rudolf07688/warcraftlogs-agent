"""REST: list selectable models (startup-validated set — US4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth.dependencies import require_session
from ..model_state import get_model_state
from ..schemas import ModelsResponse
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def get_models(
    request: Request, _: RequestIdentity = Depends(require_session)
) -> ModelsResponse:
    models, default, degraded = get_model_state(request.app)
    return ModelsResponse(models=models, default=default, degraded=degraded)
