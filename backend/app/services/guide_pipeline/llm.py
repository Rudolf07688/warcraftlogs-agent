"""Model calls for the pipeline: structured output and search-grounded text, with retry.

Plain one-shot calls (research R3): the pipeline needs typed output and, for research only,
the built-in search tools — not an agent loop. ``wcl_agent.llm.generation`` runs them on the
active provider (Gemini, or Claude with web search and web fetch, feature 035) under the shared
rate-limit retry loop; this module owns validation and turns every failure into
``GuideModelError``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from wcl_agent.llm import generation
from wcl_agent.llm.model_retry import RetryPolicy

from ...config import settings

logger = logging.getLogger(__name__)


class GuideModelError(Exception):
    """A pipeline model call failed or returned output that does not fit its schema."""


@dataclass(frozen=True)
class GroundedText:
    """Search-grounded model text plus the sources the search returned."""

    text: str
    sources: list[dict] = field(default_factory=list)  # [{title, uri}]


def _policy() -> RetryPolicy:
    return RetryPolicy(
        attempts=settings.wcl_model_retry_attempts,
        initial_s=settings.wcl_model_retry_initial_s,
        max_s=settings.wcl_model_retry_max_s,
        budget_s=settings.wcl_model_retry_budget_s,
    )


async def generate_structured(
    model: str,
    prompt: str,
    schema: type[BaseModel],
    *,
    temperature: float = 0.2,
) -> Any:
    """A tool-less call whose JSON reply is validated against ``schema`` (a model class;
    wrap lists in a container model).

    One retry on output that does not validate; then ``GuideModelError``.
    """
    last_error: Exception | None = None
    for _ in range(2):
        try:
            raw = await generation.generate_json(
                model, prompt, schema, policy=_policy(), temperature=temperature
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a pipeline model error
            raise GuideModelError(f"{type(exc).__name__}: {exc}") from exc
        try:
            return schema.model_validate_json(raw)
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning("structured output from %s did not validate: %s", model, exc)
    raise GuideModelError(f"invalid structured output: {last_error}")


async def generate_grounded(model: str, prompt: str, *, fetch_domains: Sequence[str]) -> GroundedText:
    """A research call with web search built in; ``fetch_domains`` are the only pages the model
    may open (empty: none). Claude searches that all failed hold the run (clarify Q4)."""
    try:
        grounded = await generation.generate_grounded(
            model, prompt, fetch_domains=fetch_domains, policy=_policy()
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a pipeline model error
        raise GuideModelError(f"{type(exc).__name__}: {exc}") from exc
    if grounded.search_errors and not grounded.sources:
        raise GuideModelError(f"web search failed: {', '.join(grounded.search_errors)}")
    if not grounded.text:
        raise GuideModelError("grounded call returned no text")
    return GroundedText(grounded.text, grounded.sources)
