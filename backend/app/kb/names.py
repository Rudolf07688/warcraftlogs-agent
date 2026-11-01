"""The chunk writers' one seam to the shared name resolver (043 ← 044 sc-304).

Chunk filters must use exactly the values 044's search filters on, so every class, spec,
difficulty and name a chunker stores goes through here, and from here through
``services/name_resolver``. Unlike the resolver, nothing here raises: an unknown value is
stored as unknown (None), never guessed.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import KnownPlayer, UserCharacter
from ..services.name_resolver import DIFFICULTY_NAMES, ResolutionError, name_key, resolve_class, resolve_class_spec
from .chunks import PlayerRef

__all__ = ["class_spec", "difficulty_name", "mentioned_characters", "name_key", "player"]

MAX_MENTIONS = 20
_KNOWN_PLAYERS_SCAN = 2000  # like the resolver: the newest known players
_WORD = re.compile(r"[^\W\d_]+")  # WoW names are letters only: "Vagxsu's" names Vagxsu


def class_spec(class_value: str | None, spec_value: str | None = None) -> tuple[str | None, str | None, str | None]:
    """(class, spec, role) as roster filter values, None where unknown."""
    if not class_value:
        return None, None, None
    try:
        cls = resolve_class(class_value)
    except ResolutionError:
        return None, None, None
    if not spec_value:
        return cls, None, None
    try:
        resolved = resolve_class_spec(spec_value, class_name=cls)
    except ResolutionError:
        return cls, None, None
    return resolved.class_name, resolved.spec, resolved.role


def player(name: str, class_value: str | None = None, spec_value: str | None = None, id: int | None = None) -> PlayerRef:
    cls, spec, _ = class_spec(class_value, spec_value)
    return PlayerRef(name=name, key=name_key(name), class_name=cls, spec=spec, id=id)


def difficulty_name(difficulty: int | None) -> str | None:
    return DIFFICULTY_NAMES.get(difficulty) if difficulty is not None else None


async def mentioned_characters(session: AsyncSession, tenant_id: uuid.UUID, text: str) -> tuple[PlayerRef, ...]:
    """The workspace's own characters and known players that ``text`` names, in order of first
    mention (at most :data:`MAX_MENTIONS`). Reads only this workspace's rows (explicit tenant
    predicate on top of RLS)."""
    words = list(dict.fromkeys(name_key(w) for w in _WORD.findall(text)))
    if not words:
        return ()
    own = await session.execute(
        select(UserCharacter.name, UserCharacter.class_name, UserCharacter.active_spec).where(
            UserCharacter.tenant_id == tenant_id
        )
    )
    known = await session.execute(
        select(KnownPlayer.name, KnownPlayer.class_name, KnownPlayer.spec)
        .where(KnownPlayer.tenant_id == tenant_id)
        .order_by(KnownPlayer.last_seen_at.desc())
        .limit(_KNOWN_PLAYERS_SCAN)
    )
    people: dict[str, tuple[str, str | None, str | None]] = {}
    for name, cls, spec in [*own, *known]:  # profile rows first, so their class/spec wins
        people.setdefault(name_key(name), (name, cls, spec))
    found = [player(*people[w]) for w in words if w in people]
    return tuple(found[:MAX_MENTIONS])
