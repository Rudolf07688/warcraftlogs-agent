"""Async data-access helpers for conversations and messages."""

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
    Message,
    TrackedRaid,
    UserCharacter,
)


async def create_conversation(
    session: AsyncSession, model: str, title: str | None = None
) -> Conversation:
    conv = Conversation(model=model, title=title or "New chat")
    session.add(conv)
    await session.flush()  # populate id/timestamps
    return conv


async def get_conversation(session: AsyncSession, conv_id: uuid.UUID) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conv_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def list_conversations(session: AsyncSession) -> list[Conversation]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def delete_conversation(session: AsyncSession, conv_id: uuid.UUID) -> bool:
    result = await session.execute(delete(Conversation).where(Conversation.id == conv_id))
    return result.rowcount > 0


async def _next_seq(session: AsyncSession, conv_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Message.seq), -1)).where(
            Message.conversation_id == conv_id
        )
    )
    return int(result.scalar_one()) + 1


async def add_message(
    session: AsyncSession,
    conv_id: uuid.UUID,
    role: str,
    content: str,
    status: str = "complete",
) -> Message:
    seq = await _next_seq(session, conv_id)
    msg = Message(conversation_id=conv_id, role=role, content=content, seq=seq, status=status)
    session.add(msg)
    # Touch the conversation so the sidebar re-orders and title can be set.
    conv = await session.get(Conversation, conv_id)
    if conv is not None:
        if role == "user" and (conv.title in (None, "", "New chat")):
            conv.title = content[:60]
    await session.flush()
    return msg


async def list_messages(session: AsyncSession, conv_id: uuid.UUID) -> list[Message]:
    result = await session.execute(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq)
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
    # Backfill label/metadata if it was previously only the bare code.
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
    report_code: str,
    label: str,
    zone: str | None = None,
    guild: str | None = None,
    report_started_at: datetime | None = None,
    conversation_id: uuid.UUID | None = None,
    encounters: list[dict] | None = None,
) -> TrackedRaid:
    """Insert a raid on first capture, or touch ``last_asked_at`` on re-reference.

    Dedup is by ``report_code`` (FR-002); re-referencing never creates duplicates.
    The insert is race-safe (US2): two concurrent first-time references converge to
    one row — a losing insert catches the unique-violation and updates instead. Any
    supplied ``encounters`` are merged with what's already stored (never duplicated).
    """
    existing = await session.execute(
        select(TrackedRaid).where(TrackedRaid.report_code == report_code)
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

    # First time we've seen this report — attempt the insert. If a concurrent first
    # reference won the race, the unique constraint on report_code rejects ours; we
    # roll back the failed insert and adopt the winner's row instead. (This runs
    # before any other capture work in the turn, so the rollback discards nothing
    # else — the user message was already committed in a prior transaction.)
    raid = TrackedRaid(
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
                select(TrackedRaid).where(TrackedRaid.report_code == report_code)
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


async def list_tracked_raids(session: AsyncSession) -> list[TrackedRaid]:
    result = await session.execute(
        select(TrackedRaid).order_by(TrackedRaid.last_asked_at.desc())
    )
    return list(result.scalars().all())


async def get_tracked_raid(session: AsyncSession, report_code: str) -> TrackedRaid | None:
    result = await session.execute(
        select(TrackedRaid).where(TrackedRaid.report_code == report_code)
    )
    return result.scalar_one_or_none()


# --- Captured graphs (US5) ----------------------------------------------------


async def add_captured_graph(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    report_code: str,
    data_type: str,
    graph_json: dict,
    fight_id: int = 0,
    source_id: int = 0,
    message_seq: int | None = None,
) -> CapturedGraph:
    graph = CapturedGraph(
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
    session: AsyncSession, conv_id: uuid.UUID
) -> list[CapturedGraph]:
    result = await session.execute(
        select(CapturedGraph)
        .where(CapturedGraph.conversation_id == conv_id)
        .order_by(
            CapturedGraph.message_seq.is_(None),  # non-null seqs first
            CapturedGraph.message_seq,
            CapturedGraph.created_at,
        )
    )
    return list(result.scalars().all())


# --- Artifacts (feature 005 / US2) --------------------------------------------


async def add_artifact(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    kind: str,
    title: str,
    spec_json: dict,
    message_seq: int | None = None,
) -> Artifact:
    artifact = Artifact(
        conversation_id=conversation_id,
        kind=kind,
        title=title,
        spec_json=spec_json,
        message_seq=message_seq,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def list_artifacts(session: AsyncSession, conv_id: uuid.UUID) -> list[Artifact]:
    result = await session.execute(
        select(Artifact)
        .where(Artifact.conversation_id == conv_id)
        .order_by(
            Artifact.message_seq.is_(None),  # non-null seqs first
            Artifact.message_seq,
            Artifact.created_at,
        )
    )
    return list(result.scalars().all())


# --- Turn-end capture linkage (feature 005, shared by US2 + US5) ---------------


async def assign_message_seq_to_turn_captures(
    session: AsyncSession, conv_id: uuid.UUID, seq: int
) -> None:
    """Stamp ``message_seq=seq`` on this conversation's still-unassigned captures.

    Turns are serialized per socket, so the ``message_seq IS NULL`` artifacts and
    captured graphs for this conversation are exactly the captures of the turn that
    just produced the agent message at ``seq``. Links them so per-message reports and
    reload-time rendering can scope captures to their originating message.
    """
    await session.execute(
        update(Artifact)
        .where(Artifact.conversation_id == conv_id, Artifact.message_seq.is_(None))
        .values(message_seq=seq)
    )
    await session.execute(
        update(CapturedGraph)
        .where(CapturedGraph.conversation_id == conv_id, CapturedGraph.message_seq.is_(None))
        .values(message_seq=seq)
    )
    await session.flush()


# --- Global profile (feature 005 / US1) ---------------------------------------


async def get_self_character(session: AsyncSession) -> UserCharacter | None:
    result = await session.execute(
        select(UserCharacter).where(UserCharacter.role == "self")
    )
    return result.scalars().first()


async def list_friend_characters(session: AsyncSession) -> list[UserCharacter]:
    result = await session.execute(
        select(UserCharacter)
        .where(UserCharacter.role == "friend")
        .order_by(UserCharacter.created_at)
    )
    return list(result.scalars().all())


async def get_guild_profile(session: AsyncSession) -> GuildProfile | None:
    result = await session.execute(select(GuildProfile))
    return result.scalars().first()


async def get_profile(
    session: AsyncSession,
) -> tuple[UserCharacter | None, list[UserCharacter], GuildProfile | None]:
    """Return the single global profile: (self, friends, guild)."""
    return (
        await get_self_character(session),
        await list_friend_characters(session),
        await get_guild_profile(session),
    )


async def upsert_self(
    session: AsyncSession, *, name: str, server: str, region: str
) -> UserCharacter:
    """Create or replace the single ``self`` character. Resets the guide lifecycle."""
    existing = await get_self_character(session)
    if existing is not None:
        existing.name = name
        existing.server = server
        existing.region = region
        existing.class_name = None
        existing.active_spec = None
        existing.guide_markdown = None
        existing.guide_status = "pending"
        existing.guide_updated_at = None
        await session.flush()
        return existing
    char = UserCharacter(
        role="self", name=name, server=server, region=region, guide_status="pending"
    )
    session.add(char)
    await session.flush()
    return char


async def add_friend(
    session: AsyncSession, *, name: str, server: str, region: str
) -> UserCharacter:
    """Add a friend character. Raises IntegrityError on an identical duplicate."""
    char = UserCharacter(
        role="friend", name=name, server=server, region=region, guide_status="pending"
    )
    session.add(char)
    await session.flush()
    return char


async def delete_friend(session: AsyncSession, char_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(UserCharacter).where(
            UserCharacter.id == char_id, UserCharacter.role == "friend"
        )
    )
    return result.rowcount > 0


async def set_guild(
    session: AsyncSession, *, name: str, server: str, region: str
) -> GuildProfile:
    """Replace the single main guild (one-main-guild limit, FR-003)."""
    await session.execute(delete(GuildProfile))
    guild = GuildProfile(
        name=name, server=server, region=region, summary_status="pending"
    )
    session.add(guild)
    await session.flush()
    return guild


async def delete_guild(session: AsyncSession) -> bool:
    result = await session.execute(delete(GuildProfile))
    return result.rowcount > 0


async def get_character(session: AsyncSession, char_id: uuid.UUID) -> UserCharacter | None:
    return await session.get(UserCharacter, char_id)


async def set_character_guide(
    session: AsyncSession,
    char_id: uuid.UUID,
    *,
    class_name: str | None = None,
    active_spec: str | None = None,
    markdown: str | None = None,
    status: str,
) -> UserCharacter | None:
    """Persist guide-task output (US6). Stamps ``guide_updated_at`` when ready."""
    char = await session.get(UserCharacter, char_id)
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
    markdown: str | None = None,
    status: str,
) -> GuildProfile | None:
    """Persist guild progression-summary output (US6)."""
    guild = await session.get(GuildProfile, guild_id)
    if guild is None:
        return None
    if markdown is not None:
        guild.summary_markdown = markdown
    guild.summary_status = status
    if status == "ready":
        guild.summary_updated_at = datetime.now(timezone.utc)
    await session.flush()
    return guild
