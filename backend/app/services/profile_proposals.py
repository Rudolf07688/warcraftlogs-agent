"""Profile change proposals: the two-phase write behind the agent's profile tool (feature 029).

Design C9–C14 and ``#proposal-service-api``
(documentation/designs/self-aware-agent/capabilities-and-tools.html). The agent tool only
*creates* a proposal; nothing on the profile changes until the user approves it, which runs
:func:`execute_proposal` exactly once: re-validated under the tenant's profile lock, then
written in bulk (sc-223, sc-225).

Every function opens its own tenant-scoped transaction for the acting identity (the reads can
join the caller's instead), so the transport (031's frame and REST routes) needs no session of
its own, and every query is scoped to the tenant **and** the user: another tenant's or user's
proposal is ``not_found``.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import get_args

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.cache.normalize import server_slug
from wcl_agent.game.roster import resolve_spec, roster_snapshot

from ..db import repository as repo
from ..db.models import ProfileProposal, UserCharacter
from ..db.timestamps import as_utc
from ..repositories import profile_proposals as rows
from ..schemas import (
    CharacterIn,
    ProfileChangeIn,
    ProfileProposalOut,
    ProposalItemOut,
    ProposalItemResult,
    ProposalValidation,
)
from ..tenancy.context import RequestIdentity, tenant_scope
from .guide import schedule_character_guides

logger = logging.getLogger(__name__)

MAX_PROPOSAL_ITEMS = 30  # a retail raid has at most 30 players, so a whole raid fits (C13)
PROPOSAL_TTL = timedelta(minutes=30)  # C10; correctness doesn't depend on it (re-validation)

# Identity rules for proposals (C12), on top of the manual-entry ``CharacterIn`` schema. They
# follow the game's naming rules; widen them here if a real name or realm is refused. The
# name rule is the prompt-injection guard (C14): a name with spaces, digits or punctuation
# can't be applied, so it never reaches the profile or the next turn's preamble.
_NAME = re.compile(r"[^\W\d_]{2,12}")
# Realm form (sc-221): words of letters or digits joined by single spaces, hyphens or
# apostrophes, optionally one "(Suffix)" ("Aggra (Português)"), at most _REALM_CHARS. The
# longest real realm names are about 22 characters ("Culte de la Rive noire"), so a sentence
# can't persist into later preambles through an approved realm.
_REALM = re.compile(r"[^\W_]+(?:[ '\-][^\W_]+)*(?: \([^\W_]+\))?")
_REALM_CHARS = 24
_REGIONS = frozenset({"us", "eu", "kr", "tw", "cn"})
_CLIP = 100  # CharacterIn's maximum; longer values are invalid anyway (bounds the stored row)

_ROLE = {"own": "self", "friend": "friend"}  # proposal target -> user_characters.role
_ACTIONS = get_args(ProfileChangeIn.model_fields["action"].annotation)
_LIMITS = {"own": ("character_limit", repo.MAX_OWN_CHARACTERS), "friend": ("friend_limit", repo.MAX_FRIENDS)}

_MESSAGES = {
    "duplicate_character": "Already one of your characters.",
    "duplicate_friend": "Already a friend.",
    "already_friend": "Saved as a friend; remove it there first.",
    "already_own": "One of your own characters.",
    "character_limit": f"You can register up to {repo.MAX_OWN_CHARACTERS} characters.",
    "friend_limit": "The friend limit is reached.",
    "invalid_name": "Not a valid character name.",
    "invalid_realm": "Not a valid realm name.",
    "invalid_region": "Region must be one of US, EU, KR, TW or CN.",
    "duplicate_item": "Listed twice in this proposal.",
    "not_found": "Not in that list.",
    "no_change": "Already has that raid role.",
    "invalid_item": "Not a valid character entry.",
}


# Runs inside the decision's transaction, under the proposal's row lock (sc-242).
TransitionHook = Callable[[AsyncSession, ProfileProposalOut], Awaitable[None]]


class ProposalError(Exception):
    """A proposal call was refused. ``code``: ``not_found`` (missing, another tenant's or
    another user's: no disclosure), ``proposal_expired``, ``proposal_cancelled`` or
    ``proposal_applied``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


# --- Validation (C12, C13) ---------------------------------------------------------


@dataclass
class _Entry:
    """One character of the profile as validation sees it (a working copy)."""

    character_id: uuid.UUID | None  # None for an add earlier in the same proposal
    raid_role: str | None


_Key = tuple[tuple[str, str, str], str]  # (identity, target)
_OTHER = {"own": "friend", "friend": "own"}


def _identity_key(name: str, realm: str, region: str) -> tuple[str, str, str]:
    return name.strip().casefold(), server_slug(realm), region.strip().lower()


def _profile(chars: Sequence[UserCharacter]) -> dict[_Key, _Entry]:
    """The working copy, keyed by identity **and** target (sc-223): a legacy profile can hold
    one character in both roles under two realm spellings, and both stay addressable."""
    return {
        (_identity_key(c.name, c.server, c.region), "own" if c.role == "self" else "friend"): _Entry(
            c.id, c.raid_role
        )
        for c in chars
    }


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _field(raw: object, key: str) -> object:
    return raw.get(key) if isinstance(raw, Mapping) else getattr(raw, key, None)


def _parse(raw: object) -> tuple[ProfileChangeIn | None, str | None]:
    """One proposed item as the tool receives it; returns (change, None) or (None, code).

    sc-241: ADK converts the tool's list one item at a time and hands over an item it
    couldn't convert as the raw value, so every item is checked here on its own. A missing or
    blank realm or region gets its own code before the generic ``invalid_item``.
    """
    if not isinstance(raw, (ProfileChangeIn, Mapping)):
        return None, "invalid_item"
    if _blank(_field(raw, "realm")):
        return None, "invalid_realm"
    if _blank(_field(raw, "region")):
        return None, "invalid_region"
    if isinstance(raw, ProfileChangeIn):
        return raw, None
    try:
        return ProfileChangeIn.model_validate(raw), None
    except ValidationError:
        return None, "invalid_item"


def _text(value: object) -> str:
    return value.strip()[:_CLIP] if isinstance(value, str) else ""


def _class_spec(class_name: object, spec: object) -> tuple[str | None, str | None]:
    """Class and spec as the roster names them, else None (sc-221): never the model's text.

    A class the roster knows keeps its key when only the spec doesn't resolve.
    """
    class_text, spec_text = _text(class_name), _text(spec)
    if not class_text:
        return None, None
    entry = resolve_spec(class_text, spec_text) if spec_text else None
    if entry is not None:
        return entry.class_name, entry.spec_display
    roster = roster_snapshot()
    for key in roster.classes():  # the class alone: match it with any one of its specs
        entry = resolve_spec(class_text, roster.specs_for(key)[0])
        if entry is not None:
            return entry.class_name, None
    return None, None


def _skipped(index: int, raw: object, code: str) -> ProposalItemOut:
    """The card row of an item that couldn't be read; display only, never applied."""
    action, target = _field(raw, "action"), _field(raw, "target")
    class_name, spec = _class_spec(_field(raw, "class_name"), _field(raw, "spec"))
    return ProposalItemOut(
        index=index,
        action=action if action in _ACTIONS else "add",
        target=target if target in _ROLE else "friend",
        name=_text(_field(raw, "name")),
        realm=_text(_field(raw, "realm")),
        region=_text(_field(raw, "region")).lower(),
        class_name=class_name,
        spec=spec,
        validation=ProposalValidation(ok=False, code=code, message=_MESSAGES[code]),
    )


def _check(change: ProfileChangeIn, profile: dict[_Key, _Entry], counts: dict, seen: set) -> tuple[str | None, _Entry | None]:
    """Validate one change against the working profile; returns (code, matched entry)."""
    try:
        CharacterIn(name=change.name, server=change.realm, region=change.region, raid_role=change.raid_role)
    except ValidationError:
        return "invalid_item", None
    if not _NAME.fullmatch(change.name.strip()):
        return "invalid_name", None
    realm = change.realm.strip()
    if len(realm) > _REALM_CHARS or not _REALM.fullmatch(realm):
        return "invalid_realm", None
    if change.region.strip().lower() not in _REGIONS:
        return "invalid_region", None
    key = _identity_key(change.name, change.realm, change.region)
    if (key, change.target) in seen:
        return "duplicate_item", None
    existing = profile.get((key, change.target))
    if change.action == "add":
        if existing is not None:
            return ("duplicate_character" if change.target == "own" else "duplicate_friend"), None
        if (key, _OTHER[change.target]) in profile:
            return ("already_friend" if change.target == "own" else "already_own"), None
        code, limit = _LIMITS[change.target]
        if counts[change.target] >= limit:
            return code, None
        return None, None
    if existing is None:
        return "not_found", None
    if change.action == "update" and existing.raid_role == change.raid_role:
        return "no_change", None
    return None, existing


def _validate(
    changes: Sequence[ProfileChangeIn | object], chars: Sequence[UserCharacter]
) -> list[ProposalItemOut]:
    """Validate the changes in order over a working copy of the profile.

    Each valid change updates the copy, so limits count earlier adds in the same proposal
    and a "move" (remove a friend, then add it as an own character) validates.
    """
    profile = _profile(chars)
    counts = {"own": 0, "friend": 0}
    for _, target in profile:
        counts[target] += 1
    seen: set = set()
    items: list[ProposalItemOut] = []
    for index, raw in enumerate(changes):
        change, code = _parse(raw)
        if change is None:
            items.append(_skipped(index, raw, code))
            continue
        code, existing = _check(change, profile, counts, seen)
        class_name, spec = _class_spec(change.class_name, change.spec)
        item = ProposalItemOut(
            index=index,
            action=change.action,
            target=change.target,
            name=change.name.strip()[:_CLIP],
            realm=change.realm.strip()[:_CLIP],
            region=change.region.strip().lower()[:_CLIP],
            class_name=class_name,
            spec=spec,
            raid_role=None if change.action == "remove" else change.raid_role,
            played_role=change.played_role,
            validation=ProposalValidation(ok=code is None, code=code, message=_MESSAGES.get(code)),
        )
        if code is None:
            key = _identity_key(change.name, change.realm, change.region)
            seen.add((key, change.target))
            if change.action == "add":
                profile[(key, change.target)] = _Entry(None, change.raid_role)
                counts[change.target] += 1
            else:
                item.character_id = existing.character_id
                if change.action == "update":
                    item.previous_raid_role = existing.raid_role
                    existing.raid_role = change.raid_role
                else:
                    del profile[(key, change.target)]
                    counts[change.target] -= 1
        items.append(item)
    return items


def _change_of(item: ProposalItemOut) -> ProfileChangeIn:
    return ProfileChangeIn(
        action=item.action,
        target=item.target,
        name=item.name,
        realm=item.realm,
        region=item.region,
        raid_role=item.raid_role,
    )


async def _load_profile(db, tenant_id: uuid.UUID) -> list[UserCharacter]:
    own = await repo.list_own_characters(db, tenant_id=tenant_id)
    return [*own, *await repo.list_friend_characters(db, tenant_id=tenant_id)]


# --- Reads ---------------------------------------------------------------------------


def _status(row: ProfileProposal, now: datetime) -> str:
    if row.status == "pending" and now >= as_utc(row.expires_at):
        return "expired"
    return row.status


def _to_out(row: ProfileProposal, now: datetime | None = None) -> ProfileProposalOut:
    return ProfileProposalOut(
        id=row.id,
        conversation_id=row.conversation_id,
        message_seq=row.message_seq,
        status=_status(row, now or _now()),
        created_at=as_utc(row.created_at),
        expires_at=as_utc(row.expires_at),
        applied_at=as_utc(row.applied_at) if row.applied_at else None,
        items=row.items,
    )


async def create_proposal(
    identity: RequestIdentity, conversation_id: uuid.UUID, changes: Sequence[ProfileChangeIn | object]
) -> ProfileProposalOut:
    """Validate the changes and store a pending proposal. Writes nothing to the profile.

    Each change is validated on its own (an item that isn't a valid change is a skipped row).

    Raises ``ValueError`` for an empty or too large list (the tool returns it as its error)
    and ``ProposalError("not_found")`` when the conversation isn't this tenant's.
    """
    if not 1 <= len(changes) <= MAX_PROPOSAL_ITEMS:
        raise ValueError(
            f"Too many changes ({len(changes)}): at most {MAX_PROPOSAL_ITEMS} per proposal; "
            "ask the user to narrow it down."
            if changes
            else "No changes to propose."
        )
    async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as db:
        if await repo.get_conversation_row(db, conversation_id, tenant_id=identity.tenant_id) is None:
            raise ProposalError("not_found")
        items = _validate(changes, await _load_profile(db, identity.tenant_id))
        now = _now()
        row = await rows.insert_proposal(
            db,
            ProfileProposal(
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                conversation_id=conversation_id,
                status="pending",
                items=[i.model_dump(mode="json") for i in items],
                created_at=now,
                expires_at=now + PROPOSAL_TTL,
            ),
        )
        out = _to_out(row, now)
    logger.info(
        "profile proposal %s created: %d items, %d valid",
        out.id, len(items), sum(i.validation.ok for i in items),
    )
    return out


@asynccontextmanager
async def _reading(identity: RequestIdentity, db: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    """The caller's transaction when it has one (already scoped to this identity), else a
    short one of our own (sc-225: a reload or a proposal frame opens no extra transaction)."""
    if db is not None:
        yield db
        return
    async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as own:
        yield own


async def get_proposal(
    identity: RequestIdentity, proposal_id: uuid.UUID, *, db: AsyncSession | None = None
) -> ProfileProposalOut:
    async with _reading(identity, db) as db:
        row = await rows.get_proposal_row(
            db, proposal_id, tenant_id=identity.tenant_id, user_id=identity.user_id
        )
        if row is None:
            raise ProposalError("not_found")
        return _to_out(row)


async def list_proposals(
    identity: RequestIdentity, conversation_id: uuid.UUID, *, db: AsyncSession | None = None
) -> list[ProfileProposalOut]:
    """Every proposal of that conversation for this user, oldest first, status computed."""
    async with _reading(identity, db) as db:
        found = await rows.list_proposal_rows(
            db, tenant_id=identity.tenant_id, user_id=identity.user_id, conversation_id=conversation_id
        )
        now = _now()
        return [_to_out(row, now) for row in found]


# --- Execute / cancel (C10, C11) ------------------------------------------------------


async def _apply(db, identity: RequestIdentity, items: list[ProposalItemOut]) -> list[uuid.UUID]:
    """Apply every still-valid item; record per-item results. Returns the added ids.

    The tenant's profile is locked first (sc-223), so re-validation against the profile as it
    is now (REST, another tab or another proposal may have changed it) is final: nothing can
    add in between. Update/remove are addressed by identity. The writes then go in bulk, one
    delete, one update and one insert for the whole proposal (sc-225); an update or remove
    whose row is gone meanwhile reports ``not_found``.
    """
    tenant_id = identity.tenant_id
    await repo.lock_profile(db, tenant_id=tenant_id)
    valid = [item for item in items if item.validation.ok]
    rechecked = _validate([_change_of(item) for item in valid], await _load_profile(db, tenant_id))
    for item in items:
        if not item.validation.ok:
            item.result = ProposalItemResult(status="skipped", code=item.validation.code)
    todo: dict[str, list[tuple[ProposalItemOut, ProposalItemOut]]] = {"remove": [], "update": [], "add": []}
    for item, now_item in zip(valid, rechecked):
        if now_item.validation.ok:
            todo[item.action].append((item, now_item))
        else:
            item.result = ProposalItemResult(status="failed", code=now_item.validation.code)

    gone = await repo.delete_characters(
        db, tenant_id=tenant_id, ids=[now.character_id for _, now in todo["remove"]]
    )
    changed = await repo.set_raid_roles(
        db, tenant_id=tenant_id, roles={now.character_id: now.raid_role for _, now in todo["update"]}
    )
    for item, now_item in todo["remove"] + todo["update"]:
        done = now_item.character_id in (gone if item.action == "remove" else changed)
        item.result = (
            ProposalItemResult(status="applied", character_id=now_item.character_id)
            if done
            else ProposalItemResult(status="failed", code="not_found")
        )
    new = await repo.add_characters(
        db,
        tenant_id=tenant_id,
        rows=[
            dict(role=_ROLE[now.target], name=now.name, server=now.realm, region=now.region, raid_role=now.raid_role)
            for _, now in todo["add"]
        ],
    )
    for (item, _), char in zip(todo["add"], new):
        item.character_id = char.id
        item.result = ProposalItemResult(status="applied", character_id=char.id)
    return [char.id for char in new]


async def execute_proposal(
    identity: RequestIdentity, proposal_id: uuid.UUID, *, on_transition: TransitionHook | None = None
) -> ProfileProposalOut:
    """Apply the valid items of a pending proposal, exactly once (C11).

    One transaction: the row lock, every item and the final status. An applied proposal
    comes back unchanged and nothing is written, so a double click or a second tab is safe.
    ``on_transition`` runs in that transaction only when this call applied it (sc-242).
    """
    async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as db:
        row = await rows.get_proposal_row(
            db, proposal_id, tenant_id=identity.tenant_id, user_id=identity.user_id, for_update=True
        )
        if row is None:
            raise ProposalError("not_found")
        now = _now()
        status = _status(row, now)
        if status == "applied":
            return _to_out(row, now)
        if status == "cancelled":
            raise ProposalError("proposal_cancelled")
        if status == "expired":
            row.status = "expired"  # stored; raised below, after this transaction commits
            added = None
        else:
            items = [ProposalItemOut.model_validate(item) for item in row.items]
            added = await _apply(db, identity, items)
            row.items = [item.model_dump(mode="json") for item in items]
            row.status = "applied"
            row.applied_at = now
            out = _to_out(row, now)
            if on_transition is not None:
                await on_transition(db, out)
    if added is None:
        raise ProposalError("proposal_expired")
    # After the commit: the guide jobs read the characters in their own transactions.
    schedule_character_guides(added, identity.tenant_id)
    logger.info(
        "profile proposal %s applied: %s",
        out.id, ", ".join(f"{i.index}={i.result.status}" for i in out.items),
    )
    return out


async def cancel_proposal(
    identity: RequestIdentity, proposal_id: uuid.UUID, *, on_transition: TransitionHook | None = None
) -> ProfileProposalOut:
    """pending → cancelled. Cancelling twice is a no-op; an expired proposal stays expired.

    ``on_transition`` runs in the same transaction only when this call cancelled it (sc-242).
    """
    async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as db:
        row = await rows.get_proposal_row(
            db, proposal_id, tenant_id=identity.tenant_id, user_id=identity.user_id, for_update=True
        )
        if row is None:
            raise ProposalError("not_found")
        now = _now()
        status = _status(row, now)
        if status == "applied":
            raise ProposalError("proposal_applied")
        row.status = "cancelled" if status == "pending" else status
        out = _to_out(row, now)
        if status == "pending" and on_transition is not None:
            await on_transition(db, out)
        return out
