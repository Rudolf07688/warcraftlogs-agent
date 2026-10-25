"""Generated conversation titles (feature 019 / sc-155).

After a chat's first complete reply, a cheap model names the chat from that exchange,
off the chat path and at most once (research R3–R8). ``clean_title`` turns the model's
reply into a plain one-line title; it is split out so its rules are unit-testable
without a model call.
"""

from __future__ import annotations

import re

TITLE_MAX_LEN = 60

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
