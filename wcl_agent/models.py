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

import contextvars
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


def _gather_threads(calls: list[Callable[[], T]], max_workers: int = 4) -> list[T | BaseException]:
    """Run blocking SDK probes concurrently; results in input order, errors in their slot."""
    if not calls:
        return []

    def capture(call: Callable[[], T]) -> T | BaseException:
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - handed back to the caller in its slot
            return exc

    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls))) as pool:
        futures = [pool.submit(contextvars.copy_context().run, capture, c) for c in calls]
        return [f.result() for f in futures]


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


# PERF-015: a probe that hangs must not hold up startup (readiness waits on discovery).
PROBE_TIMEOUT_S = 10


def _probe_gemini(client: Any, model_id: str) -> bool:
    try:
        from google.genai import types

        client.models.generate_content(
            model=model_id,
            contents="hello",
            config=types.GenerateContentConfig(
                max_output_tokens=1,
                http_options=types.HttpOptions(timeout=PROBE_TIMEOUT_S * 1000),
            ),
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
            timeout=PROBE_TIMEOUT_S,
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
    infra_ran = False
    # PERF-015: probe every candidate concurrently instead of one after another; results
    # keep the configured order (Gemini first, then Anthropic).
    probes: list[tuple[str, Any]] = []

    if gemini_ids:
        gclient = _make_gemini_client()
        if gclient is not None:
            infra_ran = True
            probes += [(m, lambda m=m: _probe_gemini(gclient, m)) for m in gemini_ids]

    if anthropic_ids:
        aclient = _make_anthropic_client()
        if aclient is not None:
            infra_ran = True
            probes += [(m, lambda m=m: _probe_anthropic(aclient, m)) for m in anthropic_ids]

    results = _gather_threads([probe for _, probe in probes], max_workers=8)
    validated = [m for (m, _), ok in zip(probes, results) if ok is True]

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
