"""REST: list selectable models."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..schemas import ModelsResponse

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def get_models() -> ModelsResponse:
    return ModelsResponse(models=settings.model_list, default=settings.default_model)
