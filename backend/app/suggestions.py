"""Predicted follow-up questions for a finished answer (US1).

A small, best-effort, non-streaming generation that proposes up to three short
next questions a user might click. It runs after the turn is already `done`
(PERF-005), on a fixed cheap model with thinking off and a short timeout, and it
fails closed: any error or timeout yields no suggestions rather than breaking the turn.

The parsing is split out (`parse_followups`) so the cap/dedup/trivial rules are
unit-testable without a model call.
"""

from __future__ import annotations

import asyncio
import json
import os
import re

MAX_SUGGESTIONS = 3
_MAX_LEN = 160  # drop model runaway; display truncates further client-side.

# A cheap, fast model for suggestions regardless of the chat model (they don't
# need the premium one, and a thinking chat model would be slow). Overridable via env;
# always a Gemini id (genai path).
_SUGGEST_MODEL = os.getenv("WCL_SUGGEST_MODEL", "gemini-3.6-flash")
# Upper bound on the whole suggestion call; past it the turn simply has no suggestions.
SUGGEST_TIMEOUT_S = 4.0
_MAX_OUTPUT_TOKENS = 256

_client = None  # one google-genai client per process (PERF-005), created on first use


def _get_client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client()
    return _client

_PROMPT = (
    "You suggest up to 3 short follow-up questions a user might ask next, based on "
    "the assistant's answer below. Questions must be answerable by the same Warcraft "
    "Logs analyst and phrased from the user's point of view (e.g. 'What are the parse "
    "scores for everyone?'). Return ONLY a JSON array of strings, max 3, no prose. "
    "If no useful follow-up applies (e.g. a greeting, an error, or a trivial reply), "
    'return [].\n\nUSER QUESTION:\n{question}\n\nASSISTANT ANSWER:\n{answer}\n'
)


def parse_followups(raw: str) -> list[str]:
    """Parse model output into ≤3 clean, de-duplicated suggestion strings.

    Accepts a JSON array or a loose newline/bulleted list; strips numbering,
    bullets, quotes and markdown; drops empties and over-long lines.
    """
    if not raw:
        return []
    text = raw.strip()
    candidates: list[str] = []
    parsed_json = False

    # Prefer a JSON array if one is present anywhere in the output.
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                candidates = [str(x) for x in data]
                parsed_json = True  # trust the array even if empty
        except (ValueError, TypeError):
            parsed_json = False

    # Only fall back to line-splitting when no JSON array was parsed.
    if not parsed_json and not candidates:
        candidates = text.splitlines()

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        s = item.strip()
        # Strip leading list markers: "1.", "-", "*", "•", quotes.
        s = re.sub(r'^\s*(?:[-*•]|\d+[.)])\s*', "", s)
        s = s.strip().strip('"').strip("'").strip()
        if not s or len(s) > _MAX_LEN:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)
        if len(cleaned) >= MAX_SUGGESTIONS:
            break
    return cleaned


async def generate_followups(model: str | None, question: str, answer: str) -> list[str]:
    """Return up to 3 follow-up questions for this turn; [] on any failure or timeout.

    Always uses the cheap suggest model (``model``, the chat model, is no longer reused —
    PERF-005) through the async google-genai client, with thinking off. Never raises —
    suggestions are a non-critical enhancement.
    """
    answer = (answer or "").strip()
    if not answer or answer == "(no response)":
        return []
    prompt = _PROMPT.format(question=question, answer=answer)
    try:
        from google.genai import types

        # Feature 011 / FR-012: deliberately no retry_options and no backoff here — a
        # rate-limited suggestion call must fail fast and silently.
        resp = await asyncio.wait_for(
            _get_client().aio.models.generate_content(
                model=_SUGGEST_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            ),
            timeout=SUGGEST_TIMEOUT_S,
        )
        return parse_followups(getattr(resp, "text", "") or "")
    except Exception:  # noqa: BLE001 - best-effort (incl. TimeoutError); never break the turn
        return []
