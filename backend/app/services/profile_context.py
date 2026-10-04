"""Build the per-turn "KNOWN PLAYER CONTEXT" preamble (feature 005 / US1).

The preamble is prepended to the model input for a turn only — never persisted or
shown to the user. It lets Barnaby resolve "me/my/us/our/our guild" to the saved
identities without the user retyping names, while population-level questions are
answered normally (the instruction in ``wcl_agent/agent.py`` encodes that rule).

Feature 007 extends the single preamble (Constitution Principle I — no second path):
- US1 appends a bounded ``RECENTLY SEEN (this account)`` block of captured metadata
  (known raids/players/encounters/guilds) so follow-ups across the user's
  conversations reuse it instead of re-querying Warcraft Logs.
- US4 appends each character's effective raid role (override or spec-inferred).

When the profile is empty AND no captured metadata is supplied, the preamble is ""
so behavior is identical to having no profile at all (FR-006, FR-011, SC-003, SC-008).
"""

from __future__ import annotations

from wcl_agent.constants import role_for_spec

from ..db.models import GuildProfile, KnownEncounter, KnownPlayer, TrackedRaid, UserCharacter

# Keep injected guide text bounded so a few long guides can't blow up the token
# budget. Total across all included guides is capped; each guide is also trimmed.
_PER_GUIDE_CHARS = 1500
_TOTAL_GUIDE_CHARS = 4000
# Fixed cap for the whole captured-metadata block (US1), independent of history size.
_RECENT_CHARS = 1500

_HEADER = (
    "KNOWN PLAYER CONTEXT (use only when the question is about the user, their "
    "friends, or their guild; answer population-level questions normally):"
)

_RECENT_HEADER = (
    "RECENTLY SEEN (this account) — reuse these already-resolved details instead of "
    "re-querying Warcraft Logs when a follow-up refers to them:"
)

# Display labels for the effective raid role appended to a character line (US4).
_ROLE_LABELS = {"tank": "Tank", "healer": "Healer", "dps": "DPS"}


def _ident(c: UserCharacter) -> str:
    spec = " — ".join(x for x in [c.class_name, c.active_spec] if x)
    base = f"{c.name}-{c.server} ({c.region})"
    label = f"{base} — {spec}" if spec else base
    # US4: append the effective raid role (user override, else inferred from spec). Unset
    # ⇒ omitted so the line stays byte-identical to pre-feature output (FR-030).
    role = c.raid_role or role_for_spec(c.active_spec)
    if role:
        label = f"{label} — {_ROLE_LABELS.get(role, role)}"
    return label


def _player_ident(p: KnownPlayer) -> str:
    extra = " — ".join(x for x in [p.class_name, p.spec] if x)
    base = f"{p.name}-{p.server} ({p.region})"
    return f"{base} — {extra}" if extra else base


def _encounter_ident(e: KnownEncounter) -> str:
    return f"{e.encounter_name} ({e.zone_name})" if e.zone_name else e.encounter_name


def _trim(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _recent_block(
    known_raids: list[TrackedRaid],
    known_players: list[KnownPlayer],
    known_encounters: list[KnownEncounter],
    known_guilds: list[str],
    profile_chars: list[UserCharacter],
) -> str:
    """Compose the bounded captured-metadata block, or "" when nothing was captured."""
    # Reconcile discovered players against profile characters (no double-listing).
    profile_ids = {
        (c.name.lower(), c.server.lower(), c.region.lower()) for c in profile_chars
    }

    lines: list[str] = []
    raids = [r.label for r in known_raids if r.label]
    if raids:
        lines.append("- Raids: " + "; ".join(raids))
    players = [
        _player_ident(p)
        for p in known_players
        if (p.name.lower(), p.server.lower(), p.region.lower()) not in profile_ids
    ]
    if players:
        lines.append("- Players: " + "; ".join(players))
    encounters = [_encounter_ident(e) for e in known_encounters if e.encounter_name]
    if encounters:
        lines.append("- Encounters: " + "; ".join(encounters))
    guilds = [g for g in known_guilds if g]
    if guilds:
        lines.append("- Guilds: " + "; ".join(guilds))

    if not lines:
        return ""
    return _trim("\n".join([_RECENT_HEADER, *lines]), _RECENT_CHARS)


def build_preamble(
    self_character: UserCharacter | None,
    friends: list[UserCharacter],
    guild: GuildProfile | None,
    *,
    known_raids: list[TrackedRaid] = (),
    known_players: list[KnownPlayer] = (),
    known_encounters: list[KnownEncounter] = (),
    known_guilds: list[str] = (),
) -> str:
    """Compose the capped standing-context block, or "" when there's nothing to inject.

    The profile portion is byte-identical to pre-feature output; the captured-metadata
    block is appended only when non-empty (FR-005, FR-011).
    """
    profile_chars = ([self_character] if self_character else []) + list(friends)

    # --- Profile block (unchanged output shape) -------------------------------
    profile_lines: list[str] = []
    if self_character is not None or friends or guild is not None:
        profile_lines.append(_HEADER)
        if self_character is not None:
            profile_lines.append(f"- You (self): {_ident(self_character)}")
        if friends:
            profile_lines.append("- Friends: " + "; ".join(_ident(f) for f in friends))
        if guild is not None:
            profile_lines.append(f"- Main guild: {guild.name}-{guild.server} ({guild.region})")

        # Append any ready spec guides, bounded in total.
        guided = [
            c
            for c in profile_chars
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
                profile_lines.extend(guide_lines)

        if guild is not None and guild.summary_status == "ready" and guild.summary_markdown:
            profile_lines.append("- Guild recent progression:")
            profile_lines.append(f"  {_trim(guild.summary_markdown, _PER_GUIDE_CHARS)}")

    # --- Captured-metadata block (US1, feature 007) ---------------------------
    recent = _recent_block(
        list(known_raids),
        list(known_players),
        list(known_encounters),
        list(known_guilds),
        profile_chars,
    )

    blocks: list[str] = []
    if profile_lines:
        blocks.append("\n".join(profile_lines))
    if recent:
        blocks.append(recent)
    return "\n".join(blocks)
