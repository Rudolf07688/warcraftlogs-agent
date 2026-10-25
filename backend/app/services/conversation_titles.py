"""Generated conversation titles (feature 019 / sc-155).

After a chat's first complete reply, a cheap model names the chat from that exchange,
off the chat path and at most once (research R3–R8). ``clean_title`` turns the model's
reply into a plain one-line title; it is split out so its rules are unit-testable
without a model call.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable

from wcl_agent.llm.model_retry import RetryPolicy, current_turn, generate_with_retry

from .. import suggestions
from ..db import repository as repo
from ..tenancy.context import RequestIdentity, tenant_scope
from . import background

logger = logging.getLogger(__name__)

TITLE_MAX_LEN = 60
# Hard cap on the whole model call, retries included, so a hung model can't keep the
# task alive (plan note b). The DB writes around it are single short statements.
TITLE_TIMEOUT_S = 15.0
# One retry on a rate limit, well inside the timeout; a second 429 keeps the old title.
_POLICY = RetryPolicy(attempts=2, initial_s=2.0, max_s=5.0, budget_s=8.0)
_MAX_OUTPUT_TOKENS = 32
_MAX_QUESTION_CHARS = 1000
_MAX_ANSWER_CHARS = 2000

_PROMPT = (
    "Write a short title (at most 8 words) for this chat between a World of Warcraft "
    "player and a Warcraft Logs analyst, in the language of the player's message. "
    "Return only the title: no quotes, no markdown, no trailing period.\n\n"
    "PLAYER:\n{question}\n\nANALYST:\n{answer}\n"
)

_LABEL = re.compile(r"^\s*title\s*:\s*", re.IGNORECASE)
_MARKDOWN = re.compile(r"[*_`#>~]+")
_QUOTES = "\"'“”‘’«»"
_TRAILING = " .,:;-–—"


def clean_title(raw: str | None) -> str:
    """A plain title of at most ``TITLE_MAX_LEN`` characters from model output.

    Keeps the first non-empty line, drops a ``Title:`` label, markdown markers and
    surrounding quotes, collapses whitespace, and cuts an over-long title at a word
    boundary. Returns ``""`` when nothing usable is left (the caller keeps the old title).
    """
    line = next((ln for ln in (raw or "").splitlines() if ln.strip()), "")
    text = _LABEL.sub("", _MARKDOWN.sub("", line))
    text = " ".join(text.split()).strip(_QUOTES + " ").rstrip(_TRAILING)
    if len(text) > TITLE_MAX_LEN:
        cut = text[: TITLE_MAX_LEN + 1].rfind(" ")
        text = text[: cut if cut > 0 else TITLE_MAX_LEN].rstrip(_TRAILING)
    return text if any(ch.isalnum() for ch in text) else ""


async def generate_title(question: str, answer: str) -> str:
    """One cheap, non-streaming model call through the shared rate-limit retry loop.

    Uses the follow-up suggestions model and client (one per process). Returns the cleaned
    title, or ``""``; errors propagate to ``retitle_conversation``, which owns them.
    """
    from google.genai import types

    prompt = _PROMPT.format(
        question=question[:_MAX_QUESTION_CHARS], answer=answer[:_MAX_ANSWER_CHARS]
    )
    config = types.GenerateContentConfig(
        max_output_tokens=_MAX_OUTPUT_TOKENS,
        temperature=0.2,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    async def call_model():
        yield await suggestions._get_client().aio.models.generate_content(
            model=suggestions._SUGGEST_MODEL, contents=prompt, config=config
        )

    async for response in generate_with_retry(call_model, _POLICY):
        return clean_title(getattr(response, "text", "") or "")
    return ""


async def retitle_conversation(
    conv_id: uuid.UUID,
    identity: RequestIdentity,
    question: str,
    answer: str,
    notify: Callable[[str], Awaitable[None]],
) -> None:
    """Give a default-named chat its generated title, at most once; never raises.

    Claims the chat first (``auto → generated``), so a failed attempt is never retried and
    the first-message title stays (FR-017). ``notify`` sends the client frame best-effort:
    the title is already saved, so a closed socket only means the next list load shows it.
    """
    tenant_id = identity.tenant_id
    try:
        async with tenant_scope(tenant_id, user_id=identity.user_id) as session:
            if not await repo.claim_title_generation(session, conv_id, tenant_id=tenant_id):
                return
        current_turn.set(None)  # a title retry must never report into a chat turn
        async with asyncio.timeout(TITLE_TIMEOUT_S):
            title = await generate_title(question, answer)
        if not title:
            return
        async with tenant_scope(tenant_id, user_id=identity.user_id) as session:
            if not await repo.set_generated_title(session, conv_id, title, tenant_id=tenant_id):
                return  # deleted meanwhile
    except Exception:  # noqa: BLE001 - incl. timeout and rate limit; the old title stays
        logger.warning("conversation %s: title not generated", conv_id, exc_info=True)
        return
    try:
        await notify(title)
    except Exception:  # noqa: BLE001 - e.g. the socket closed meanwhile
        logger.debug("conversation %s: title frame not sent", conv_id, exc_info=True)


def schedule_title(
    conv_id: uuid.UUID,
    identity: RequestIdentity,
    question: str,
    answer: str,
    notify: Callable[[str], Awaitable[None]],
) -> None:
    """Run ``retitle_conversation`` in the background (plan note a): ``background.spawn``
    keeps a strong reference until it finishes and dedups per chat in this process."""
    background.spawn(
        retitle_conversation(conv_id, identity, question, answer, notify),
        key=("conversation-title", conv_id),
    )
