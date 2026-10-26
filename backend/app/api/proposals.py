"""REST: approve or cancel an agent's profile change proposal (feature 031 / sc-207).

The confirmation card's two actions (design: participants-and-confirmation.html #transport,
#followup). Both call only the proposal service (feature 029), which applies or cancels in its
own tenant- and user-scoped transaction; these handlers never touch profile rows. When a call
moves a proposal out of ``pending``, one short follow-up line is saved as an agent message in
the proposal's chat. It's built from the per-item results, not by the model, and is never added
to the agent's session (D10).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException

from ..auth.dependencies import require_csrf
from ..db import repository as repo
from ..schemas import MessageOut, ProfileProposalOut, ProposalDecisionOut, ProposalItemOut
from ..services import profile_proposals
from ..tenancy.context import RequestIdentity, tenant_scope

router = APIRouter(prefix="/api/profile/proposals", tags=["profile"])

# The card's labels for the proposal codes (frontend ProposalCard.tsx), so the line and the
# card use the same words.
_LABELS = {
    "duplicate_friend": "already a friend",
    "already_friend": "already a friend",
    "already_own": "your own character",
    "duplicate_character": "your own character",
    "character_limit": "character limit reached",
    "friend_limit": "friend limit (50) reached",
    "invalid_name": "name not valid",
    "invalid_realm": "realm unknown, add by hand",
    "invalid_region": "region unknown",
    "invalid_item": "not valid",
    "duplicate_item": "listed twice",
    "not_found": "no longer in your profile",
    "no_change": "already set",
}
_VERB = {"add": "add", "remove": "remove", "update": "set the role of"}
# Items refused for their identity: their name may be hostile text from a log (029 C14), so the
# saved line never repeats it, only the reason.
_INVALID = frozenset({"invalid_name", "invalid_realm", "invalid_region", "invalid_item"})
# The line is rendered as Markdown, so names are escaped (defence in depth: valid names are
# letters only).
_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~])")

CANCELLED_TEXT = "Cancelled. Your profile is unchanged."


def _label(code: str | None) -> str:
    return _LABELS.get(code or "", "not applied")


def _name(item: ProposalItemOut) -> str:
    return _MARKDOWN.sub(r"\\\1", item.name)


def _entries(n: int) -> str:
    return f"{n} {'entry' if n == 1 else 'entries'}"


def _names(items: list[ProposalItemOut]) -> str:
    names = [_name(it) for it in items]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _count(n: int, target: str) -> str:
    noun = "friend" if target == "friend" else "own character"
    return f"{n} {noun}{'' if n == 1 else 's'}"


def follow_up_text(proposal: ProfileProposalOut) -> str:
    """The line Barnaby posts after a decision; it restates the per-item results only."""
    if proposal.status == "cancelled":
        return CANCELLED_TEXT
    applied = [it for it in proposal.items if it.result and it.result.status == "applied"]
    skipped = [it for it in proposal.items if it.result and it.result.status == "skipped"]
    failed = [it for it in proposal.items if it.result and it.result.status == "failed"]

    parts: list[str] = []
    for action, verb in (("add", "Added"), ("remove", "Removed")):
        for target in ("friend", "own"):
            group = [it for it in applied if it.action == action and it.target == target]
            if group:
                parts.append(f"{verb} {_count(len(group), target)}: {_names(group)}.")
    for it in applied:
        if it.action == "update":
            role = f"Set {_name(it)}'s role to {it.raid_role}." if it.raid_role else f"Cleared {_name(it)}'s role."
            parts.append(role)
    if not applied:
        parts.append("Nothing was applied.")
    if skipped:
        listed = [f"{_name(it)} ({_label(it.result.code)})" for it in skipped if it.result.code not in _INVALID]
        for code in sorted({it.result.code for it in skipped} & _INVALID):
            n = sum(it.result.code == code for it in skipped)
            listed.append(f"{_entries(n)} ({_label(code)})")
        parts.append(f"Skipped {len(skipped)}: {', '.join(listed)}.")
    for it in failed:
        who = "1 entry" if it.result.code in _INVALID else _name(it)
        parts.append(f"Couldn't {_VERB[it.action]} {who} ({_label(it.result.code)}).")
    if failed:
        parts.append("Nothing else changed.")
    elif applied:
        parts.insert(0, "Done.")
    return " ".join(parts)


def _refused(code: str) -> HTTPException:
    return HTTPException(status_code=404 if code == "not_found" else 409, detail=code)


async def _decide(
    identity: RequestIdentity,
    proposal_id: uuid.UUID,
    action: Callable[[RequestIdentity, uuid.UUID], Awaitable[ProfileProposalOut]],
) -> ProposalDecisionOut:
    try:
        before = await profile_proposals.get_proposal(identity, proposal_id)
        after = await action(identity, proposal_id)
    except profile_proposals.ProposalError as exc:
        raise _refused(exc.code) from exc
    if after.status == "expired":  # cancel reports an expired proposal instead of raising
        raise _refused("proposal_expired")
    # Only the call that left ``pending`` saves a line: a repeat (double click, second tab)
    # returns the stored state with no second message.
    follow_up = None
    if before.status == "pending":
        async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as session:
            msg = await repo.add_message(
                session,
                after.conversation_id,
                "agent",
                follow_up_text(after),
                tenant_id=identity.tenant_id,
            )
            await session.refresh(msg)
            follow_up = MessageOut.model_validate(msg)
    return ProposalDecisionOut(proposal=after, follow_up=follow_up)


@router.post("/{proposal_id}/approve", response_model=ProposalDecisionOut)
async def approve(
    proposal_id: uuid.UUID, identity: RequestIdentity = Depends(require_csrf)
) -> ProposalDecisionOut:
    """Apply every valid item (D4); idempotent, so a repeat returns the stored result."""
    return await _decide(identity, proposal_id, profile_proposals.execute_proposal)


@router.post("/{proposal_id}/cancel", response_model=ProposalDecisionOut)
async def cancel(
    proposal_id: uuid.UUID, identity: RequestIdentity = Depends(require_csrf)
) -> ProposalDecisionOut:
    """Cancel the whole proposal; nothing on the profile is written."""
    return await _decide(identity, proposal_id, profile_proposals.cancel_proposal)
