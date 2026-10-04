"""Async data-access helpers for conversations, messages, raids, graphs, profile.

Every tenant-owned function takes a **keyword-only ``tenant_id: UUID``** and includes it
in the SQL predicate / insert (feature 006, contracts/tenant-scoping.md). No function ever
fetches a tenant-owned row by id alone — a foreign/absent id returns ``None`` → the caller
maps that to ``404`` (never fetch-then-authorize). Child rows (messages, graphs, artifacts)
receive ``tenant_id`` from the parent at insert time.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..services.encounters import merge_encounters
from .models import (
    Artifact,
    CapturedGraph,
    Conversation,
    GuildProfile,
    KnownEncounter,
    KnownPlayer,
    Message,
    TrackedRaid,
    UserCharacter,
)


async def create_conversation(
    session: AsyncSession, model: str, title: str | None = None, *, tenant_id: uuid.UUID
) -> Conversation:
    conv = Conversation(model=model, title=title or "New chat", tenant_id=tenant_id)
    session.add(conv)
    await session.flush()  # populate id/timestamps
    return conv


async def get_conversation(
    session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conv_id, Conversation.tenant_id == tenant_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def list_conversations(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.tenant_id == tenant_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def delete_conversation(
    session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> bool:
    result = await session.execute(
        delete(Conversation).where(
            Conversation.id == conv_id, Conversation.tenant_id == tenant_id
        )
    )
    return result.rowcount > 0


async def _next_seq(session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Message.seq), -1)).where(
            Message.conversation_id == conv_id, Message.tenant_id == tenant_id
        )
    )
    return int(result.scalar_one()) + 1


async def add_message(
    session: AsyncSession,
    conv_id: uuid.UUID,
    role: str,
    content: str,
    status: str = "complete",
    *,
    tenant_id: uuid.UUID,
) -> Message:
    seq = await _next_seq(session, conv_id, tenant_id=tenant_id)
    msg = Message(
        conversation_id=conv_id,
        role=role,
        content=content,
        seq=seq,
        status=status,
        tenant_id=tenant_id,
    )
    session.add(msg)
    # Touch the conversation so the sidebar re-orders and title can be set.
    conv = await get_conversation(session, conv_id, tenant_id=tenant_id)
    if conv is not None:
        if role == "user" and (conv.title in (None, "", "New chat")):
            conv.title = content[:60]
    await session.flush()
    return msg


async def list_messages(
    session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conv_id, Message.tenant_id == tenant_id)
        .order_by(Message.seq)
    )
    return list(result.scalars().all())


# --- Tracked raids (US1) ------------------------------------------------------


def _apply_raid_update(
    raid: TrackedRaid,
    *,
    label: str,
    zone: str | None,
    guild: str | None,
    report_started_at: datetime | None,
    conversation_id: uuid.UUID | None,
    encounters: list[dict] | None,
) -> None:
    """Touch recency and backfill metadata on an existing raid (US2 merge)."""
    raid.last_asked_at = datetime.now(timezone.utc)
    if conversation_id is not None:
        raid.last_conversation_id = conversation_id
    if label and (not raid.label or raid.label == raid.report_code):
        raid.label = label
    if zone and not raid.zone:
        raid.zone = zone
    if guild and not raid.guild:
        raid.guild = guild
    if report_started_at and not raid.report_started_at:
        raid.report_started_at = report_started_at
    if encounters:
        merged = merge_encounters(raid.encounters, encounters)
        if merged != (raid.encounters or []):
            raid.encounters = merged


async def upsert_tracked_raid(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    report_code: str,
    label: str,
    zone: str | None = None,
    guild: str | None = None,
    report_started_at: datetime | None = None,
    conversation_id: uuid.UUID | None = None,
    encounters: list[dict] | None = None,
) -> TrackedRaid:
    """Insert a raid on first capture (per tenant), or touch ``last_asked_at`` on re-ref.

    Dedup is by ``(tenant_id, report_code)``; the insert is race-safe (a losing insert
    catches the unique-violation and updates the winner's row instead).
    """
    existing = await session.execute(
        select(TrackedRaid).where(
            TrackedRaid.tenant_id == tenant_id, TrackedRaid.report_code == report_code
        )
    )
    raid = existing.scalar_one_or_none()
    if raid is not None:
        _apply_raid_update(
            raid,
            label=label,
            zone=zone,
            guild=guild,
            report_started_at=report_started_at,
            conversation_id=conversation_id,
            encounters=encounters,
        )
        await session.flush()
        return raid

    raid = TrackedRaid(
        tenant_id=tenant_id,
        report_code=report_code,
        label=label,
        zone=zone,
        guild=guild,
        report_started_at=report_started_at,
        last_conversation_id=conversation_id,
        encounters=encounters or None,
    )
    session.add(raid)
    try:
        await session.flush()
        return raid
    except IntegrityError:
        await session.rollback()
        raid = (
            await session.execute(
                select(TrackedRaid).where(
                    TrackedRaid.tenant_id == tenant_id, TrackedRaid.report_code == report_code
                )
            )
        ).scalar_one()
        _apply_raid_update(
            raid,
            label=label,
            zone=zone,
            guild=guild,
            report_started_at=report_started_at,
            conversation_id=conversation_id,
            encounters=encounters,
        )
        await session.flush()
        return raid


async def list_tracked_raids(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[TrackedRaid]:
    result = await session.execute(
        select(TrackedRaid)
        .where(TrackedRaid.tenant_id == tenant_id)
        .order_by(TrackedRaid.last_asked_at.desc())
    )
    return list(result.scalars().all())


async def get_tracked_raid(
    session: AsyncSession, report_code: str, *, tenant_id: uuid.UUID
) -> TrackedRaid | None:
    result = await session.execute(
        select(TrackedRaid).where(
            TrackedRaid.tenant_id == tenant_id, TrackedRaid.report_code == report_code
        )
    )
    return result.scalar_one_or_none()


# --- Known entities (feature 007 / US1) ---------------------------------------


async def upsert_known_player(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    server: str,
    region: str,
    class_name: str | None = None,
    spec: str | None = None,
    source: str | None = None,
) -> KnownPlayer:
    """Insert a known player on first sighting (per tenant), or touch recency + backfill.

    Dedup is by ``(tenant_id, name, server, region)``. A re-sighting touches
    ``last_seen_at`` and fills in a previously-null ``class_name``/``spec``/``source``.
    Caller wraps this in a savepoint so a unique-violation can't poison sibling captures.
    """
    now = datetime.now(timezone.utc)
    existing = (
        await session.execute(
            select(KnownPlayer).where(
                KnownPlayer.tenant_id == tenant_id,
                KnownPlayer.name == name,
                KnownPlayer.server == server,
                KnownPlayer.region == region,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.last_seen_at = now
        if class_name and not existing.class_name:
            existing.class_name = class_name
        if spec and not existing.spec:
            existing.spec = spec
        if source and not existing.source:
            existing.source = source
        await session.flush()
        return existing
    player = KnownPlayer(
        tenant_id=tenant_id,
        name=name,
        server=server,
        region=region,
        class_name=class_name,
        spec=spec,
        source=source,
        last_seen_at=now,
    )
    session.add(player)
    await session.flush()
    return player


async def upsert_known_encounter(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: int,
    encounter_name: str,
    zone_id: int | None = None,
    zone_name: str | None = None,
) -> KnownEncounter:
    """Insert a known encounter on first sighting, or touch recency + backfill zone fields.

    Dedup is by ``(tenant_id, encounter_id)``. Caller wraps this in a savepoint.
    """
    now = datetime.now(timezone.utc)
    existing = (
        await session.execute(
            select(KnownEncounter).where(
                KnownEncounter.tenant_id == tenant_id,
                KnownEncounter.encounter_id == encounter_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.last_seen_at = now
        if zone_id and not existing.zone_id:
            existing.zone_id = zone_id
        if zone_name and not existing.zone_name:
            existing.zone_name = zone_name
        await session.flush()
        return existing
    encounter = KnownEncounter(
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        encounter_name=encounter_name,
        zone_id=zone_id,
        zone_name=zone_name,
        last_seen_at=now,
    )
    session.add(encounter)
    await session.flush()
    return encounter


async def list_recent_known_players(
    session: AsyncSession, *, tenant_id: uuid.UUID, limit: int = 15
) -> list[KnownPlayer]:
    result = await session.execute(
        select(KnownPlayer)
        .where(KnownPlayer.tenant_id == tenant_id)
        .order_by(KnownPlayer.last_seen_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_recent_known_encounters(
    session: AsyncSession, *, tenant_id: uuid.UUID, limit: int = 10
) -> list[KnownEncounter]:
    result = await session.execute(
        select(KnownEncounter)
        .where(KnownEncounter.tenant_id == tenant_id)
        .order_by(KnownEncounter.last_seen_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_recent_known_guilds(
    session: AsyncSession, *, tenant_id: uuid.UUID, limit: int = 10
) -> list[str]:
    """Distinct non-null guild names from tracked raids, most-recent first (derived — no table)."""
    result = await session.execute(
        select(TrackedRaid.guild, func.max(TrackedRaid.last_asked_at).label("seen"))
        .where(TrackedRaid.tenant_id == tenant_id, TrackedRaid.guild.isnot(None))
        .group_by(TrackedRaid.guild)
        .order_by(func.max(TrackedRaid.last_asked_at).desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


# --- Captured graphs (US5) ----------------------------------------------------


async def add_captured_graph(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    report_code: str,
    data_type: str,
    graph_json: dict,
    fight_id: int = 0,
    source_id: int = 0,
    message_seq: int | None = None,
) -> CapturedGraph:
    graph = CapturedGraph(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        report_code=report_code,
        data_type=data_type,
        graph_json=graph_json,
        fight_id=fight_id,
        source_id=source_id,
        message_seq=message_seq,
    )
    session.add(graph)
    await session.flush()
    return graph


async def list_captured_graphs(
    session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> list[CapturedGraph]:
    result = await session.execute(
        select(CapturedGraph)
        .where(
            CapturedGraph.conversation_id == conv_id, CapturedGraph.tenant_id == tenant_id
        )
        .order_by(
            CapturedGraph.message_seq.is_(None),
            CapturedGraph.message_seq,
            CapturedGraph.created_at,
        )
    )
    return list(result.scalars().all())


# --- Artifacts (feature 005 / US2) --------------------------------------------


async def add_artifact(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    kind: str,
    title: str,
    spec_json: dict,
    message_seq: int | None = None,
) -> Artifact:
    artifact = Artifact(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        kind=kind,
        title=title,
        spec_json=spec_json,
        message_seq=message_seq,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def list_artifacts(
    session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> list[Artifact]:
    result = await session.execute(
        select(Artifact)
        .where(Artifact.conversation_id == conv_id, Artifact.tenant_id == tenant_id)
        .order_by(
            Artifact.message_seq.is_(None),
            Artifact.message_seq,
            Artifact.created_at,
        )
    )
    return list(result.scalars().all())


# --- Turn-end capture linkage (feature 005, shared by US2 + US5) ---------------


async def assign_message_seq_to_turn_captures(
    session: AsyncSession, conv_id: uuid.UUID, seq: int, *, tenant_id: uuid.UUID
) -> None:
    """Stamp ``message_seq=seq`` on this conversation's still-unassigned captures (tenant-scoped)."""
    await session.execute(
        update(Artifact)
        .where(
            Artifact.conversation_id == conv_id,
            Artifact.tenant_id == tenant_id,
            Artifact.message_seq.is_(None),
        )
        .values(message_seq=seq)
    )
    await session.execute(
        update(CapturedGraph)
        .where(
            CapturedGraph.conversation_id == conv_id,
            CapturedGraph.tenant_id == tenant_id,
            CapturedGraph.message_seq.is_(None),
        )
        .values(message_seq=seq)
    )
    await session.flush()


# --- Profile (feature 005 / US1) ---------------------------------------------


async def get_self_character(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> UserCharacter | None:
    result = await session.execute(
        select(UserCharacter).where(
            UserCharacter.tenant_id == tenant_id, UserCharacter.role == "self"
        )
    )
    return result.scalars().first()


async def list_friend_characters(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[UserCharacter]:
    result = await session.execute(
        select(UserCharacter)
        .where(UserCharacter.tenant_id == tenant_id, UserCharacter.role == "friend")
        .order_by(UserCharacter.created_at)
    )
    return list(result.scalars().all())


async def get_guild_profile(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> GuildProfile | None:
    result = await session.execute(
        select(GuildProfile).where(GuildProfile.tenant_id == tenant_id)
    )
    return result.scalars().first()


async def get_profile(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> tuple[UserCharacter | None, list[UserCharacter], GuildProfile | None]:
    """Return the tenant's profile: (self, friends, guild)."""
    return (
        await get_self_character(session, tenant_id=tenant_id),
        await list_friend_characters(session, tenant_id=tenant_id),
        await get_guild_profile(session, tenant_id=tenant_id),
    )


async def upsert_self(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    server: str,
    region: str,
    raid_role: str | None = None,
) -> UserCharacter:
    """Create or replace the tenant's single ``self`` character. Resets the guide lifecycle.

    ``raid_role`` is the user override (US4); passing ``None`` leaves the role unset so
    the effective role falls back to the spec-inferred default once the guide resolves.
    """
    existing = await get_self_character(session, tenant_id=tenant_id)
    if existing is not None:
        existing.name = name
        existing.server = server
        existing.region = region
        existing.class_name = None
        existing.active_spec = None
        existing.raid_role = raid_role
        existing.guide_markdown = None
        existing.guide_status = "pending"
        existing.guide_updated_at = None
        await session.flush()
        return existing
    char = UserCharacter(
        tenant_id=tenant_id,
        role="self",
        name=name,
        server=server,
        region=region,
        raid_role=raid_role,
        guide_status="pending",
    )
    session.add(char)
    await session.flush()
    return char


async def add_friend(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    server: str,
    region: str,
    raid_role: str | None = None,
) -> UserCharacter:
    """Add a friend character. Raises IntegrityError on an identical duplicate (per tenant)."""
    char = UserCharacter(
        tenant_id=tenant_id,
        role="friend",
        name=name,
        server=server,
        region=region,
        raid_role=raid_role,
        guide_status="pending",
    )
    session.add(char)
    await session.flush()
    return char


async def update_friend_role(
    session: AsyncSession,
    char_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID,
    raid_role: str | None,
) -> UserCharacter | None:
    """Set a friend's raid-role override in place (US4 / FR-028). ``None`` clears it.

    Returns the updated character, or ``None`` when the id is not a friend of this tenant
    (the caller maps that to 404). Never creates a new row.
    """
    result = await session.execute(
        select(UserCharacter).where(
            UserCharacter.id == char_id,
            UserCharacter.tenant_id == tenant_id,
            UserCharacter.role == "friend",
        )
    )
    char = result.scalar_one_or_none()
    if char is None:
        return None
    char.raid_role = raid_role
    await session.flush()
    return char


async def delete_friend(
    session: AsyncSession, char_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> bool:
    result = await session.execute(
        delete(UserCharacter).where(
            UserCharacter.id == char_id,
            UserCharacter.tenant_id == tenant_id,
            UserCharacter.role == "friend",
        )
    )
    return result.rowcount > 0


async def set_guild(
    session: AsyncSession, *, tenant_id: uuid.UUID, name: str, server: str, region: str
) -> GuildProfile:
    """Replace the tenant's single main guild (one-main-guild limit, FR-003)."""
    await session.execute(delete(GuildProfile).where(GuildProfile.tenant_id == tenant_id))
    guild = GuildProfile(
        tenant_id=tenant_id, name=name, server=server, region=region, summary_status="pending"
    )
    session.add(guild)
    await session.flush()
    return guild


async def delete_guild(session: AsyncSession, *, tenant_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(GuildProfile).where(GuildProfile.tenant_id == tenant_id)
    )
    return result.rowcount > 0


async def get_character(
    session: AsyncSession, char_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> UserCharacter | None:
    result = await session.execute(
        select(UserCharacter).where(
            UserCharacter.id == char_id, UserCharacter.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


async def set_character_guide(
    session: AsyncSession,
    char_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID,
    class_name: str | None = None,
    active_spec: str | None = None,
    markdown: str | None = None,
    status: str,
) -> UserCharacter | None:
    """Persist guide-task output (US6). Stamps ``guide_updated_at`` when ready."""
    char = await get_character(session, char_id, tenant_id=tenant_id)
    if char is None:
        return None
    if class_name is not None:
        char.class_name = class_name
    if active_spec is not None:
        char.active_spec = active_spec
    if markdown is not None:
        char.guide_markdown = markdown
    char.guide_status = status
    if status == "ready":
        char.guide_updated_at = datetime.now(timezone.utc)
    await session.flush()
    return char


async def set_guild_summary(
    session: AsyncSession,
    guild_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID,
    markdown: str | None = None,
    status: str,
) -> GuildProfile | None:
    """Persist guild progression-summary output (US6)."""
    result = await session.execute(
        select(GuildProfile).where(
            GuildProfile.id == guild_id, GuildProfile.tenant_id == tenant_id
        )
    )
    guild = result.scalar_one_or_none()
    if guild is None:
        return None
    if markdown is not None:
        guild.summary_markdown = markdown
    guild.summary_status = status
    if status == "ready":
        guild.summary_updated_at = datetime.now(timezone.utc)
    await session.flush()
    return guild
