"""Build the per-turn "KNOWN PLAYER CONTEXT" preamble (feature 005 / US1).

The preamble is prepended to the model input for a turn only — never persisted or
shown to the user. It lets Barnaby resolve "me/my/us/our/our guild" to the saved
identities without the user retyping names, while population-level questions are
answered normally (the instruction in ``wcl_agent/agent.py`` encodes that rule).

When the profile is empty the preamble is "" so behavior is identical to having no
profile at all (FR-006).
"""

from __future__ import annotations

from ..db.models import GuildProfile, UserCharacter

# Keep injected guide text bounded so a few long guides can't blow up the token
# budget. Total across all included guides is capped; each guide is also trimmed.
_PER_GUIDE_CHARS = 1500
_TOTAL_GUIDE_CHARS = 4000

_HEADER = (
    "KNOWN PLAYER CONTEXT (use only when the question is about the user, their "
    "friends, or their guild; answer population-level questions normally):"
)


def _ident(c: UserCharacter) -> str:
    spec = " — ".join(x for x in [c.class_name, c.active_spec] if x)
    base = f"{c.name}-{c.server} ({c.region})"
    return f"{base} — {spec}" if spec else base


def _trim(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def build_preamble(
    self_character: UserCharacter | None,
    friends: list[UserCharacter],
    guild: GuildProfile | None,
) -> str:
    """Compose the capped KNOWN PLAYER CONTEXT block, or "" when the profile is empty."""
    if self_character is None and not friends and guild is None:
        return ""

    lines: list[str] = [_HEADER]
    if self_character is not None:
        lines.append(f"- You (self): {_ident(self_character)}")
    if friends:
        lines.append("- Friends: " + "; ".join(_ident(f) for f in friends))
    if guild is not None:
        lines.append(f"- Main guild: {guild.name}-{guild.server} ({guild.region})")

    # Append any ready spec guides, bounded in total.
    guided = [
        c
        for c in ([self_character] if self_character else []) + list(friends)
        if c is not None and c.guide_status == "ready" and c.guide_markdown
    ]
    if guided:
        guide_lines: list[str] = ["- Spec guides:"]
        used = 0
        for c in guided:
            if used >= _TOTAL_GUIDE_CHARS:
                break
            remaining = _TOTAL_GUIDE_CHARS - used
            body = _trim(c.guide_markdown or "", min(_PER_GUIDE_CHARS, remaining))
            if not body:
                continue
            spec = c.active_spec or "spec"
            guide_lines.append(f"  ## {c.name} — {spec}")
            guide_lines.append(f"  {body}")
            used += len(body)
        if len(guide_lines) > 1:
            lines.extend(guide_lines)

    if guild is not None and guild.summary_status == "ready" and guild.summary_markdown:
        lines.append("- Guild recent progression:")
        lines.append(f"  {_trim(guild.summary_markdown, _PER_GUIDE_CHARS)}")

    return "\n".join(lines)
