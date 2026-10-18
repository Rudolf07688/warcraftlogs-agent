"""Which content type a chat turn is about — Raid or Mythic+ (feature 015, research R8).

A pure function over the message and a little context, so the preamble picks the brief of
the right content type. What the player wrote wins over history; history (the most recent
tracked report's zone) only breaks a tie or fills silence. ``unknown`` lets the caller fall
back to Raid and say so (FR-011).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

ContentTypeGuess = Literal["raid", "mplus", "unknown"]

# Strong signals name the content type unambiguously. "key" alone is ordinary English
# ("the key mistake"), so a key only counts next to a level ("+12", "a 15 key", "key level").
_MPLUS_STRONG = re.compile(
    r"(?:\bm\+|\bmythic\s*\+|\bmythic\s*plus\b|\bkeystones?\b|\bkey\s*levels?\b|"
    r"\b\d{1,2}\s*keys?\b|\bkeys?\s*\+?\d{1,2}\b|\baffix(?:es)?\b|\bm\+\s*score\b|"
    r"(?<![\w.+])\+\s?\d{1,2}\b(?!\s*%|\.\d))",
    re.I,
)
_MPLUS_WEAK = re.compile(r"\b(?:dungeons?|depleted?)\b", re.I)
_RAID_STRONG = re.compile(r"\b(?:raid(?:s|ing|er)?|lfr|raid\s*finder)\b", re.I)
_RAID_WEAK = re.compile(
    r"\b(?:boss(?:es)?|heroic|normal|prog(?:ression)?|pulls?)\b|\bmythic\b(?!\s*(?:\+|plus))", re.I
)


def _mentions(text: str, names: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(name and name.casefold() in lowered for name in names)


def classify_content_type(
    user_text: str,
    recent_zone_name: str | None,
    mplus_zone_name: str | None,
    mplus_dungeons: Iterable[str],
    raid_bosses: Iterable[str],
) -> ContentTypeGuess:
    """``mplus`` / ``raid`` from the message, else from the most recent tracked report's
    zone, else ``unknown``.

    Strong signals (Mythic+/keystone/"+12"/a dungeon name vs raid/LFR/a boss name) decide
    first; weak words (dungeon vs boss/heroic/pull) only when no strong signal is present.
    """
    text = user_text or ""
    mplus = bool(_MPLUS_STRONG.search(text)) or _mentions(text, mplus_dungeons)
    raid = bool(_RAID_STRONG.search(text)) or _mentions(text, raid_bosses)
    if not mplus and not raid:
        mplus = bool(_MPLUS_WEAK.search(text))
        raid = bool(_RAID_WEAK.search(text))
    if mplus and not raid:
        return "mplus"
    if raid and not mplus:
        return "raid"
    if recent_zone_name:
        if mplus_zone_name and recent_zone_name.casefold() == mplus_zone_name.casefold():
            return "mplus"
        return "raid"
    return "unknown"
