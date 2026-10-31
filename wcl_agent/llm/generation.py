"""One-shot model calls on the active provider: text, JSON and search-grounded text (feature 035).

Follow-up suggestions, chat titles, findings reports and the guide pipeline ask this module for
a reply instead of calling an SDK themselves. It is part of the provider layer: with
``provider`` it is the only code that calls ``active_provider()``. A Claude id runs on the
active provider's Claude client (the Anthropic API under ``anthropic``, Model Garden under
``vertex``), a Gemini id on the genai client. Every call goes through the shared rate-limit
loop (feature 011), so the SDKs' own retries stay off.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import anthropic
from google.genai import types as genai_types
from pydantic import BaseModel

from . import provider
from .model_retry import RetryPolicy, generate_with_retry, is_anthropic_model
from .provider import ModelRole


class ModelRefused(RuntimeError):
    """Claude declined the request (``stop_reason`` ``refusal``)."""


@functools.cache
def _claude_client() -> anthropic.AsyncAnthropic | anthropic.AsyncAnthropicVertex:
    """One Claude client per process (PERF-005); the shared loop owns the retries."""
    return provider.async_anthropic_client(max_retries=0)


@functools.cache
def _genai_client() -> Any:
    """One google-genai client per process (PERF-005)."""
    return provider.genai_client()


async def _with_retry(call: Callable[[], Awaitable[Any]], policy: RetryPolicy) -> Any:
    """``call()`` once per attempt under the shared rate-limit loop."""

    async def once():
        yield await call()

    async for response in generate_with_retry(once, policy):
        return response
    raise RuntimeError("model returned no response")


def _user(prompt: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": prompt}]


def _raise_if_refused(response: anthropic.types.Message) -> None:
    """A refusal is an error, not an empty reply."""
    if response.stop_reason == "refusal":
        raise ModelRefused(f"{response.model} declined the request")


def _claude_text(response: anthropic.types.Message) -> str:
    """The reply's text blocks, joined."""
    _raise_if_refused(response)
    return "".join(block.text for block in response.content if block.type == "text")


def _thinking_off(model: str) -> dict[str, Any]:
    """The least thinking a Claude model accepts: Haiku can turn it off, while Opus and Sonnet
    5.5 reject ``disabled`` and get the lowest effort instead (clarify Q2)."""
    if "haiku" in model.lower():
        return {"thinking": {"type": "disabled"}}
    return {"output_config": {"effort": "low"}}


async def generate_text(
    prompt: str,
    role: ModelRole,
    *,
    max_tokens: int,
    policy: RetryPolicy,
    temperature: float | None = None,
    thinking: bool = True,
) -> str:
    """The reply to ``prompt`` from ``role``'s model, or ``""`` when it returns no text.

    ``temperature`` reaches Gemini only (current Claude models reject sampling values).
    ``thinking=False`` turns Gemini's thinking off and Claude's down. Raises the SDK error,
    ``ModelRateLimited`` or ``ModelRefused``; the caller owns its timeout.
    """
    model = provider.role_model(role)
    if is_anthropic_model(model):
        extra = {} if thinking else _thinking_off(model)
        response = await _with_retry(
            lambda: _claude_client().messages.create(
                model=model, max_tokens=max_tokens, messages=_user(prompt), **extra
            ),
            policy,
        )
        return _claude_text(response)
    config = genai_types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=temperature,
        thinking_config=None if thinking else genai_types.ThinkingConfig(thinking_budget=0),
    )
    response = await _with_retry(
        lambda: _genai_client().aio.models.generate_content(model=model, contents=prompt, config=config),
        policy,
    )
    return getattr(response, "text", "") or ""


# --- the guide pipeline: structured output and search-grounded research (sc-253) ----------

# Guide calls are non-streaming; this is the Anthropic SDK's default cap for that.
_GUIDE_MAX_TOKENS = 16_000
# Searches and fetches are billed per use, so one research call is capped.
_MAX_SEARCHES = 10
_MAX_FETCHES = 5
# A long server-tool turn can pause; it is resumed at most this many times.
_MAX_RESUMES = 3
_CAPABILITIES_URL = "https://platform.claude.com/settings/capabilities"


class ServerToolDisabled(RuntimeError):
    """Web search or web fetch is not enabled for the Anthropic organisation."""


@dataclass(frozen=True)
class Grounded:
    """Search-grounded text, its ``{title, uri}`` sources, and Claude's failed-search codes."""

    text: str
    sources: list[dict] = field(default_factory=list)
    search_errors: list[str] = field(default_factory=list)


async def generate_json(
    model: str,
    prompt: str,
    schema: type[BaseModel],
    *,
    policy: RetryPolicy,
    temperature: float | None = None,
) -> str:
    """The raw JSON reply, constrained to ``schema`` (not validated here)."""
    if is_anthropic_model(model):
        output_format = {"type": "json_schema", "schema": anthropic.transform_schema(schema)}
        response = await _with_retry(
            lambda: _claude_client().messages.create(
                model=model,
                max_tokens=_GUIDE_MAX_TOKENS,
                messages=_user(prompt),
                output_config={"format": output_format},
            ),
            policy,
        )
        return _claude_text(response)
    config = genai_types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
    )
    response = await _with_retry(
        lambda: _genai_client().aio.models.generate_content(model=model, contents=prompt, config=config),
        policy,
    )
    return response.text or ""


def grounding_sources(response: Any) -> list[dict]:
    """``{title, uri}`` for every web chunk in a Gemini response's grounding metadata."""
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


def _research_tools(fetch_domains: Sequence[str]) -> list[dict[str, Any]]:
    """Web search, plus web fetch limited to ``fetch_domains``. Claude on Vertex has only the
    basic search tool and no fetch (R6)."""
    if provider.active_provider() != "anthropic":
        return [{"type": "web_search_20250305", "name": "web_search", "max_uses": _MAX_SEARCHES}]
    tools: list[dict[str, Any]] = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": _MAX_SEARCHES}
    ]
    if fetch_domains:
        tools.append(
            {
                "type": "web_fetch_20260209",
                "name": "web_fetch",
                "max_uses": _MAX_FETCHES,
                "allowed_domains": list(fetch_domains),
            }
        )
    return tools


def _tool_results(blocks: list[Any]) -> tuple[list[dict], list[str]]:
    """``{title, uri}`` of every search and fetch result (first appearance wins), and the
    error codes of failed searches."""
    sources: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()

    def add(title: str | None, uri: str | None) -> None:
        if uri and uri not in seen:
            seen.add(uri)
            sources.append({"title": title, "uri": uri})

    for block in blocks:
        if block.type == "web_search_tool_result":
            if isinstance(block.content, list):
                for result in block.content:
                    add(result.title, result.url)
            else:
                errors.append(block.content.error_code)
        elif block.type == "web_fetch_tool_result" and block.content.type == "web_fetch_result":
            add(getattr(block.content.content, "title", None), block.content.url)
    return sources, errors


async def _claude_grounded(
    model: str, prompt: str, fetch_domains: Sequence[str], policy: RetryPolicy
) -> Grounded:
    tools = _research_tools(fetch_domains)
    blocks: list[Any] = []
    try:
        for _ in range(_MAX_RESUMES + 1):
            # A paused turn is resumed by sending it back unchanged, with no new user message.
            messages = _user(prompt) + ([{"role": "assistant", "content": blocks}] if blocks else [])
            response = await _with_retry(
                lambda: _claude_client().messages.create(
                    model=model, max_tokens=_GUIDE_MAX_TOKENS, messages=messages, tools=tools
                ),
                policy,
            )
            _raise_if_refused(response)
            blocks = blocks + list(response.content)
            if response.stop_reason != "pause_turn":
                break
    except anthropic.BadRequestError as exc:
        message = str(exc).lower()
        if "not enabled" in message and ("web search" in message or "web fetch" in message):
            raise ServerToolDisabled(
                "Anthropic web search or web fetch is not enabled for this organisation; an "
                f"admin can enable it at {_CAPABILITIES_URL}"
            ) from exc
        raise
    text = "".join(block.text for block in blocks if block.type == "text").strip()
    sources, errors = _tool_results(blocks)
    return Grounded(text, sources, errors)


async def generate_grounded(
    model: str, prompt: str, *, fetch_domains: Sequence[str], policy: RetryPolicy
) -> Grounded:
    """A research reply grounded in web search, with its sources.

    ``fetch_domains`` are the only domains the model may open (URL context on Gemini, web fetch
    on Claude); empty means none. Raises the SDK error, ``ModelRateLimited``, ``ModelRefused``
    or ``ServerToolDisabled``.
    """
    if is_anthropic_model(model):
        return await _claude_grounded(model, prompt, fetch_domains, policy)
    tools = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
    if fetch_domains:
        tools.append(genai_types.Tool(url_context=genai_types.UrlContext()))
    config = genai_types.GenerateContentConfig(
        temperature=0.2,
        tools=tools,
        # Built-in tools run server-side; there are no local functions to call back.
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
    )
    response = await _with_retry(
        lambda: _genai_client().aio.models.generate_content(model=model, contents=prompt, config=config),
        policy,
    )
    return Grounded((response.text or "").strip(), grounding_sources(response))
