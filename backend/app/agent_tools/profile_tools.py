"""The agent's profile tool: propose changes to the user's characters and friends (sc-205).

Design C5–C7, C14. The tool never writes the profile: it validates the changes, stores a
proposal and returns it, and the user approves or cancels it on a card (031). Who is acting
comes only from the authenticated chat turn (``current_identity`` and the ADK session),
never from arguments, so prompt injection can't pick another tenant, user or record.
"""

from __future__ import annotations

import uuid

from google.adk.tools import ToolContext

from wcl_agent.capabilities import ToolGroup

from ..schemas import ProfileChangeIn
from ..services import profile_proposals
from ..tenancy.context import current_identity


_UNAVAILABLE = "Profile changes are unavailable in this session."
_NOTE = "Nothing has changed yet. The user approves or cancels on the card."


async def propose_profile_changes(
    changes: list[ProfileChangeIn], tool_context: ToolContext
) -> dict:
    """Propose adding, re-roling or removing the user's own characters and friends; nothing changes until the user approves.

    Call it once per request with every change (1-30 items); the user sees them all on one
    card and approves or cancels. Each item: action "add" | "update" | "remove", target
    "own" | "friend", and the character's name, realm and region (us, eu, kr, tw, cn), as
    KNOWN PLAYER CONTEXT or a tool result shows them. "update" changes the raid role only.
    Set raid_role on an add only when the user asked for a role; otherwise leave it empty
    so it is inferred from the spec. played_role (the role played in a run), class_name and
    spec are shown on the card, never stored.

    Returns the proposal with a validation result per item: items with validation.ok false
    are shown as skipped and never applied, so tell the user why. Never say a change was
    made: the profile changes only after the user approves.
    """
    identity = current_identity.get()
    if identity is None or str(identity.tenant_id) != tool_context.user_id:
        return {"status": "error", "error_message": _UNAVAILABLE}
    try:
        conversation_id = uuid.UUID(tool_context.session.id)
    except ValueError:  # a disposable greeting/guide session, not a chat
        return {"status": "error", "error_message": _UNAVAILABLE}
    try:
        proposal = await profile_proposals.create_proposal(identity, conversation_id, changes)
    except ValueError as exc:
        return {"status": "error", "error_message": str(exc)}
    except profile_proposals.ProposalError:
        return {"status": "error", "error_message": _UNAVAILABLE}
    return {"status": "success", "proposal": proposal.model_dump(mode="json"), "note": _NOTE}


PROFILE_TOOLS = ToolGroup(
    "Profile",
    (propose_profile_changes,),
    note="proposals only: nothing changes until the user approves the card",
)
