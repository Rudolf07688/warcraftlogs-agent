"""REST: list selectable models (startup-validated set — US4)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..model_state import get_model_state
from ..schemas import ModelsResponse

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def get_models(request: Request) -> ModelsResponse:
    models, default, degraded = get_model_state(request.app)
    return ModelsResponse(models=models, default=default, degraded=degraded)
