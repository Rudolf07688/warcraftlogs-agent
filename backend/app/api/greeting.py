"""REST: warm Barnaby greeting for a new chat (US5).

Served from an in-process cache primed at startup; falls back to an empty greeting
(never a 500) so the client always opens a usable chat.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from ..greeting import GREETING_MODEL, get_greeting
from ..schemas import GreetingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["greeting"])


@router.get("/greeting", response_model=GreetingResponse)
async def greeting(request: Request) -> GreetingResponse:
    """Serve the warm Barnaby greeting (model-agnostic; fixed fast model).

    Awaits the startup priming task rather than regenerating, so once the server has
    warmed up the greeting is an instant cache hit.
    """
    app = request.app
    prime = getattr(app.state, "greeting_prime_task", None)
    if prime is not None:
        try:
            await prime
        except Exception:  # noqa: BLE001 - priming failure just yields an empty greeting
            pass
    try:
        text = await get_greeting(app, GREETING_MODEL)
    except Exception:  # noqa: BLE001 - never fail a new chat over the greeting
        logger.exception("Greeting endpoint failed")
        text = ""
    return GreetingResponse(greeting=text)
