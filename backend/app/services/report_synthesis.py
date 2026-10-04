"""Findings synthesis for PDF reports (feature 007 / US2-US3).

Turns the in-scope chat messages into an analytic *findings* document — what was
discovered, not a transcript — which the existing ``render_report_pdf`` renders as the
PDF body (charts attached unchanged). One shared entry point serves both the
conversation-level and per-message reports, differing only in the scoped input.

Reuses the established off-event-loop, fail-closed one-shot ``google-genai`` pattern
(see ``suggestions.py``): a plain, non-web-search model call run via
``asyncio.to_thread`` and bounded by ``asyncio.wait_for``. The model is instructed to
emit a brief "no substantive findings" document when the content has none (FR-017), so
a *successful* call is always non-empty; a genuinely empty return is treated by the
caller as a synthesis failure (FR-018).
"""

from __future__ import annotations

import asyncio
import logging

from ..config import settings

logger = logging.getLogger(__name__)

# Bound the synchronous download: synthesis must never hang a request (FR-019).
_TIMEOUT_S = 60.0
# Cap the input fed to the model so very long conversations stay within limits; oldest
# messages are dropped first so the most recent findings are always included (edge case).
_MAX_INPUT_CHARS = 24_000

_ROLE_LABELS = {"user": "User", "agent": "Analyst"}

_SYSTEM = (
    "You are a Warcraft Logs analyst writing a findings report. Read the analysis "
    "content below and produce a concise report of WHAT WAS DISCOVERED — not a "
    "transcript of the conversation. Organize by topic/encounter, not by chat turn.\n\n"
    "Use Markdown with these sections where the content supports them:\n"
    "## Summary — what was investigated (1-3 sentences)\n"
    "## Key Findings — the concrete metrics discovered (parses/percentiles, rankings, "
    "numbers), as bullet points or a table\n"
    "## Results by Encounter / Player — per-boss and/or per-player results\n"
    "## Recommendations — any concrete advice or conclusions\n\n"
    "Rules:\n"
    "- Report only findings actually present in the content; never invent data.\n"
    "- If a number was later corrected, report only the latest value.\n"
    "- If the content is greetings/chit-chat/setup/errors with no substantive analysis, "
    "respond with exactly a short document: '## No substantive findings\\n\\nThis "
    "conversation contains no analysis findings to report.'\n"
    "- Output only Markdown using headings, bullet/numbered lists, GFM tables, and "
    "$…$/$$…$$ math. No code fences, no HTML."
)


def _build_input(messages: list[dict], *, scope: str, question: str | None) -> str:
    """Assemble the model input from in-scope messages (oldest-first, char-capped)."""
    parts: list[str] = []
    if scope == "message" and question:
        parts.append(f"Originating question (context only):\n{question}\n")
    for m in messages:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        label = _ROLE_LABELS.get(m.get("role", ""), m.get("role", ""))
        parts.append(f"[{label}]\n{content}")
    text = "\n\n".join(parts)
    if len(text) > _MAX_INPUT_CHARS:
        # Drop oldest content first; keep the most recent findings.
        text = "…(earlier content truncated)…\n\n" + text[-_MAX_INPUT_CHARS:]
    return text


def _generate(model: str, prompt: str) -> str:
    """Blocking one-shot genai call (run via ``to_thread``). Non-web-search."""
    from google import genai

    client = genai.Client()
    resp = client.models.generate_content(model=model, contents=prompt)
    return (getattr(resp, "text", "") or "").strip()


async def synthesize_findings(
    messages: list[dict],
    *,
    scope: str,
    question: str | None = None,
) -> str:
    """Synthesize an analytic findings document (Markdown) from the in-scope messages.

    ``scope`` is ``"conversation"`` | ``"message"`` (prompt tuning only). Returns the
    findings Markdown; returns ``""`` only when the model produces nothing (the caller
    treats that, like an exception/timeout, as a fail-closed error per FR-018). Raises on
    model error or timeout — the caller maps that to a clean 500 with no partial file.
    """
    body = _build_input(messages, scope=scope, question=question)
    prompt = f"{_SYSTEM}\n\n--- ANALYSIS CONTENT ---\n{body}\n--- END ---\n"
    return await asyncio.wait_for(
        asyncio.to_thread(_generate, settings.wcl_report_model, prompt),
        timeout=_TIMEOUT_S,
    )
