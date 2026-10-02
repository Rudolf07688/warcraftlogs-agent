"""Warm Barnaby greeting for a new chat (US5).

Generated once per model by running a hidden ``"Greetings, Barnaby!"`` kickoff
through the normal agent stream over a disposable session, then cached in
``app.state.greeting_cache`` for the process lifetime (FR-021…025). The kickoff is
never shown to the user; only Barnaby's reply is. A generation failure yields an
empty string (never raises) so a new chat just opens clean.
"""

from __future__ import annotations

import logging

from .agent_runner import stream_response

logger = logging.getLogger(__name__)

# The hidden prompt that elicits the greeting; never surfaced to the user.
GREETING_KICKOFF = "Greetings, Barnaby!"

# The greeting is model-agnostic (just a warm hello), so it's always generated with a
# single fixed, fast model — primed once at startup — rather than per chat model. This
# keeps it a cache hit regardless of which model the user has selected.
GREETING_MODEL = "gemini-3.5-flash-lite"


def _get_cache(app) -> dict[str, str]:
    cache = getattr(app.state, "greeting_cache", None)
    if cache is None:
        cache = {}
        app.state.greeting_cache = cache
    return cache


async def _generate_greeting(model: str) -> str:
    """Run the hidden kickoff once and collect the streamed reply text."""
    session_id = f"greeting-{model}"
    tokens: list[str] = []
    try:
        async for record in stream_response(model, session_id, GREETING_KICKOFF):
            if record.get("type") == "token":
                tokens.append(record["text"])
    except Exception:  # noqa: BLE001 - greeting is best-effort; never break a new chat
        logger.exception("Greeting generation failed for model %s", model)
        return ""
    return "".join(tokens).strip()


async def get_greeting(app, model: str) -> str:
    """Return the cached greeting for ``model``, generating (and caching) on a miss.

    On generation failure returns ``""`` and caches nothing, so a later attempt can
    still succeed.
    """
    cache = _get_cache(app)
    cached = cache.get(model)
    if cached is not None:
        return cached
    greeting = await _generate_greeting(model)
    if greeting:
        cache[model] = greeting
    return greeting
