"""Single accessor for the runtime model set (US4).

At startup the lifespan probes candidate models and stores the validated set on
``app.state`` (see main.py / wcl_agent.models). Every consumer — the models
endpoint, the WebSocket, conversation creation, and raid investigation — reads it
through here so there is one source of truth for "which models are selectable"
and "what is the default". Before startup (or in tests without a lifespan) it
falls back to the configured allow-list so the app still functions.
"""

from __future__ import annotations

from .config import settings


def get_model_state(app) -> tuple[list[str], str, bool]:
    """Return ``(models, default, degraded)`` for the given FastAPI app.

    ``app`` is any object exposing ``.state`` (a FastAPI app; reachable from a
    request as ``request.app`` or a websocket as ``ws.app``).
    """
    state = getattr(app, "state", None)
    models = list(getattr(state, "models", None) or settings.model_list)
    default = getattr(state, "default_model", None) or settings.default_model
    degraded = bool(getattr(state, "models_degraded", False))
    # Guarantee the default is selectable (never return an inconsistent pair).
    if default not in models and models:
        default = models[0]
    return models, default, degraded


def is_valid_model(app, model: str) -> bool:
    models, _, _ = get_model_state(app)
    return model in models
