"""Keep old tool results out of the model context (QA PERF-004).

ADK sends the whole conversation on every model request, including every earlier tool
result (each up to ~60 kB), so the prompt grows with every turn. Before each request, the
agent's before-model callback replaces large tool results from turns older than the most
recent ``WCL_CONTEXT_KEEP_TURNS`` (default 2: the current and the previous turn) with a
compact stub. The stub keeps what the evidence rules rely on — ``status``, ``provenance``,
``completeness`` — plus short top-level fields, and says the full data can be fetched again.
Since feature 014 only character and report-summary lookups are cached, so the note tells
the model a re-fetch usually costs a new Warcraft Logs request.

Only the request is changed. ADK's request contents are shallow copies whose nested
objects are shared with the stored session events, so trimming builds new ``Content`` and
``Part`` objects and never mutates anything in place: the stored history keeps the full
results. The stub for a given result is always the same, so the provider's prefix cache
stays valid between requests.

Standalone, like the rest of ``wcl_agent`` (no backend imports).
"""

from __future__ import annotations

import json
from typing import Any

from google.adk.models.llm_request import LlmRequest
from google.genai import types as genai_types

from ..cache.cache import _env_int

DEFAULT_KEEP_TURNS = 2
DEFAULT_STUB_MIN_CHARS = 1500
_PREVIEW_CHARS = 600
_MAX_SCALAR_CHARS = 200
_KEPT_KEYS = ("status", "error_message", "provenance", "completeness")
ELIDED_NOTE = (
    "Full result from an earlier turn omitted to save context. Use the preview if it answers "
    "the question; calling the tool again costs a new Warcraft Logs request."
)


def keep_turns() -> int:
    return max(1, _env_int("WCL_CONTEXT_KEEP_TURNS", DEFAULT_KEEP_TURNS))


def stub_min_chars() -> int:
    return max(0, _env_int("WCL_CONTEXT_STUB_MIN_CHARS", DEFAULT_STUB_MIN_CHARS))


def user_turn_indices(contents: list[genai_types.Content]) -> list[int]:
    """Indices of the contents that start a user turn: user role, text, no tool result.

    Tool results also travel as user contents (``function_response`` parts), so they are
    not turn boundaries.
    """
    starts: list[int] = []
    for i, content in enumerate(contents):
        parts = content.parts or []
        if content.role != "user":
            continue
        if any(getattr(p, "function_response", None) for p in parts):
            continue
        if any(getattr(p, "text", None) for p in parts):
            starts.append(i)
    return starts


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def compact_tool_response(response: dict[str, Any]) -> dict[str, Any]:
    """A deterministic, compact stand-in for a large tool result."""
    stub: dict[str, Any] = {k: response[k] for k in _KEPT_KEYS if k in response}
    for key in sorted(response):
        if key in stub or key.startswith("_"):
            continue
        value = response[key]
        if isinstance(value, bool | int | float) or value is None:
            stub[key] = value
        elif isinstance(value, str):
            if len(value) <= _MAX_SCALAR_CHARS:
                stub[key] = value
        elif isinstance(value, list | dict):
            stub[f"{key}_count"] = len(value)
    stub["_elided"] = True
    stub["_note"] = ELIDED_NOTE
    stub["_preview"] = _dumps(response)[:_PREVIEW_CHARS]
    return stub


def trim_old_tool_results(
    llm_request: LlmRequest,
    keep: int | None = None,
    min_chars: int | None = None,
) -> int:
    """Replace large tool results older than the last ``keep`` turns with stubs.

    Returns how many results were replaced. Builds new Content/Part objects only.
    """
    keep = keep_turns() if keep is None else keep
    min_chars = stub_min_chars() if min_chars is None else min_chars
    contents = llm_request.contents
    starts = user_turn_indices(contents)
    if len(starts) <= keep:
        return 0
    boundary = starts[-keep]  # contents before this index belong to older turns
    replaced = 0
    for i in range(boundary):
        content = contents[i]
        parts = content.parts or []
        new_parts: list[genai_types.Part] | None = None
        for j, part in enumerate(parts):
            fr = getattr(part, "function_response", None)
            response = getattr(fr, "response", None) if fr is not None else None
            if not isinstance(response, dict) or len(_dumps(response)) <= min_chars:
                continue
            if new_parts is None:
                new_parts = list(parts)
            new_parts[j] = genai_types.Part(
                function_response=genai_types.FunctionResponse(
                    id=fr.id, name=fr.name, response=compact_tool_response(response)
                )
            )
            replaced += 1
        if new_parts is not None:
            contents[i] = genai_types.Content(role=content.role, parts=new_parts)
    return replaced
