"""Model calls for the pipeline: structured output and search-grounded text, with retry.

Plain ``google.genai`` calls (research R3): the pipeline needs typed output and, for
research only, the built-in search tools — not an agent loop. Every call goes through the
shared rate-limit retry loop (feature 011) via a one-item async generator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from wcl_agent.model_retry import RetryPolicy, generate_with_retry

from ...config import settings

logger = logging.getLogger(__name__)

_client = None  # one google-genai client per process, created on first use


def _get_client():
    global _client
    if _client is None:
        from wcl_agent.vertex import genai_client

        _client = genai_client()
    return _client


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


async def _generate(model: str, prompt: str, config: Any) -> Any:
    """One ``generate_content`` call under the shared rate-limit retry loop."""

    async def once():
        yield await _get_client().aio.models.generate_content(
            model=model, contents=prompt, config=config
        )

    async for response in generate_with_retry(once, _policy()):
        return response
    raise GuideModelError("model returned no response")


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
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
    )
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = await _generate(model, prompt, config)
        except GuideModelError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as a pipeline model error
            raise GuideModelError(f"{type(exc).__name__}: {exc}") from exc
        try:
            return schema.model_validate_json(response.text or "")
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning("structured output from %s did not validate: %s", model, exc)
    raise GuideModelError(f"invalid structured output: {last_error}")


def grounding_sources(response: Any) -> list[dict]:
    """``{title, uri}`` for every web chunk in the response's grounding metadata."""
    sources: list[dict] = []
    seen: set[str] = set()
    for candidate in getattr(response, "candidates", None) or []:
        gm = getattr(candidate, "grounding_metadata", None)
        for chunk in getattr(gm, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None) if web is not None else None
            if uri and uri not in seen:
                seen.add(uri)
                sources.append({"title": getattr(web, "title", None), "uri": uri})
    return sources


async def generate_grounded(model: str, prompt: str, *, url_context: bool) -> GroundedText:
    """A research call with Google Search (and, when allowed, URL context) built in."""
    from google.genai import types

    tools = [types.Tool(google_search=types.GoogleSearch())]
    if url_context:
        tools.append(types.Tool(url_context=types.UrlContext()))
    config = types.GenerateContentConfig(
        temperature=0.2,
        tools=tools,
        # Built-in tools run server-side; there are no local functions to call back.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    try:
        response = await _generate(model, prompt, config)
    except GuideModelError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced as a pipeline model error
        raise GuideModelError(f"{type(exc).__name__}: {exc}") from exc
    text = (response.text or "").strip()
    if not text:
        raise GuideModelError("grounded call returned no text")
    return GroundedText(text, grounding_sources(response))
