"""Startup model discovery + validation (US4).

Builds a candidate set (configured Gemini + Anthropic-on-Vertex ids) and keeps
only the ones that actually respond to a minimal "hello" probe. The result is
computed once at backend startup and served from ``app.state`` — there is no
per-request probing.

If the probe *infrastructure* can't run at all (Vertex unreachable, missing
credentials) or nothing passes, a documented fallback set is returned with
``degraded=True`` so the UI can show a notice and the selector is never empty
(FR-016). All calls here are blocking and are expected to run under
``asyncio.to_thread`` (see backend lifespan).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _is_anthropic(model: str) -> bool:
    return "claude" in model.lower()


def _make_gemini_client() -> Any | None:
    try:
        from google import genai

        return genai.Client()  # reads GOOGLE_* / Vertex env
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini client unavailable for model discovery: %s", exc)
        return None


def _make_anthropic_client() -> Any | None:
    try:
        from anthropic import AnthropicVertex

        region = os.getenv("WCL_ANTHROPIC_REGION") or os.getenv("GOOGLE_CLOUD_LOCATION") or "us-east5"
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        return AnthropicVertex(region=region, project_id=project)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Anthropic-on-Vertex client unavailable for model discovery: %s", exc)
        return None


def _probe_gemini(client: Any, model_id: str) -> bool:
    try:
        from google.genai import types

        client.models.generate_content(
            model=model_id,
            contents="hello",
            config=types.GenerateContentConfig(max_output_tokens=1),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("Gemini model '%s' did not pass the probe: %s", model_id, exc)
        return False


def _probe_anthropic(client: Any, model_id: str) -> bool:
    try:
        client.messages.create(
            model=model_id,
            max_tokens=1,
            messages=[{"role": "user", "content": "hello"}],
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("Anthropic model '%s' did not pass the probe: %s", model_id, exc)
        return False


def discover_models(
    *,
    gemini_ids: list[str],
    anthropic_ids: list[str],
    configured_default: str,
    fallback_models: list[str],
) -> dict:
    """Return ``{"models", "default", "degraded"}`` after probing candidates.

    - ``models``: candidate ids that responded to the probe.
    - ``default``: ``configured_default`` if it passed, else the first validated id.
    - ``degraded``: True when probing couldn't run (or found nothing) and the
      fallback set is being served instead.
    """
    validated: list[str] = []
    infra_ran = False

    if gemini_ids:
        gclient = _make_gemini_client()
        if gclient is not None:
            infra_ran = True
            validated.extend(m for m in gemini_ids if _probe_gemini(gclient, m))

    if anthropic_ids:
        aclient = _make_anthropic_client()
        if aclient is not None:
            infra_ran = True
            validated.extend(m for m in anthropic_ids if _probe_anthropic(aclient, m))

    if not infra_ran or not validated:
        models = fallback_models or [configured_default]
        default = configured_default if configured_default in models else models[0]
        logger.warning(
            "Model discovery degraded (infra_ran=%s, validated=%s); serving fallback %s",
            infra_ran,
            validated,
            models,
        )
        return {"models": models, "default": default, "degraded": True}

    default = configured_default if configured_default in validated else validated[0]
    return {"models": validated, "default": default, "degraded": False}
