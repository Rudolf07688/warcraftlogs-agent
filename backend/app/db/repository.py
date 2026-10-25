"""Async data-access helpers for conversations, messages, raids, graphs, profile.

Every tenant-owned function takes a **keyword-only ``tenant_id: UUID``** and includes it
in the SQL predicate / insert (feature 006, contracts/tenant-scoping.md). No function ever
fetches a tenant-owned row by id alone — a foreign/absent id returns ``None`` → the caller
maps that to ``404`` (never fetch-then-authorize). Child rows (messages, graphs, artifacts)
receive ``tenant_id`` from the parent at insert time.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from ..services.encounters import merge_encounters
from ..services.recent_raid_types import ListedReport, ReportDetails
from .models import (
    Artifact,
    CapturedGraph,
    Conversation,
    GuideInaccuracyReport,
    GuildProfile,
    KnownEncounter,
    KnownPlayer,
    Message,
    RecentRaid,
    RecentRaidCharacter,
    RecentRaidRefresh,
    SpecGuide,
    TrackedRaid,
    UserCharacter,
)


async def create_conversation(
    session: AsyncSession, model: str, title: str | None = None, *, tenant_id: uuid.UUID
) -> Conversation:
    # Feature 019 / FR-018: a caller that names the chat (raid investigations, recent-raid
    # kickoffs, POST with a title) marks it explicit at creation; it is never auto-renamed.
    conv = Conversation(
        model=model,
        title=title or "New chat",
        title_source="explicit" if title else "auto",
        tenant_id=tenant_id,
    )
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


async def get_conversation_row(
    session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> Conversation | None:
    """The conversation alone, without loading its messages (PERF-007: the chat turn and
    ``add_message`` only need the row; ``get_conversation`` loads the full transcript)."""
    result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id, Conversation.tenant_id == tenant_id)
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


async def set_conversation_pinned(
    session: AsyncSession, conv_id: uuid.UUID, pinned: bool, *, tenant_id: uuid.UUID
) -> Conversation | None:
    """Pin or unpin a conversation (feature 019 / sc-165); ``None`` when it isn't this
    tenant's. A repeated pin keeps the original pin time, and ``updated_at`` is set to
    itself so pinning never reorders the list by activity (FR-009)."""
    pinned_at = (
        func.coalesce(Conversation.pinned_at, datetime.now(timezone.utc)) if pinned else None
    )
    result = await session.execute(
        update(Conversation)
        .where(Conversation.id == conv_id, Conversation.tenant_id == tenant_id)
        .values(pinned_at=pinned_at, updated_at=Conversation.updated_at)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        return None
    row = await session.execute(
        select(Conversation)
        .where(Conversation.id == conv_id, Conversation.tenant_id == tenant_id)
        .execution_options(populate_existing=True)
    )
    return row.scalar_one()


async def claim_title_generation(
    session: AsyncSession, conv_id: uuid.UUID, *, tenant_id: uuid.UUID
) -> bool:
    """Claim the one generated title of a default-named chat (feature 019 / FR-016).

    A single conditional UPDATE ``auto → generated``: exactly one caller ever gets True,
    across tasks, processes and instances. Explicit, legacy and already-claimed chats
    (and other tenants' ids) give False. ``updated_at`` is left alone.
    """
    result = await session.execute(
        update(Conversation)
        .where(
            Conversation.id == conv_id,
            Conversation.tenant_id == tenant_id,
            Conversation.title_source == "auto",
        )
        .values(title_source="generated", updated_at=Conversation.updated_at)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


async def set_generated_title(
    session: AsyncSession, conv_id: uuid.UUID, title: str, *, tenant_id: uuid.UUID
) -> bool:
    """Write a generated title, only on a chat whose generation was claimed (never over
    an explicit or legacy name). False when the chat is gone or not this tenant's."""
    result = await session.execute(
        update(Conversation)
        .where(
            Conversation.id == conv_id,
            Conversation.tenant_id == tenant_id,
            Conversation.title_source == "generated",
        )
        .values(title=title, updated_at=Conversation.updated_at)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


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
    # Title the conversation from its first user message with one targeted UPDATE; the
    # transcript is never loaded here (PERF-007). ``onupdate`` bumps updated_at as before.
    if role == "user":
        await session.execute(
            update(Conversation)
            .where(
                Conversation.id == conv_id,
                Conversation.tenant_id == tenant_id,
                or_(Conversation.title.is_(None), Conversation.title.in_(("", "New chat"))),
            )
            .values(title=content[:60])
            .execution_options(synchronize_session="fetch")
        )
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
    # A savepoint, so a lost insert race rolls back only this insert — not the caller's
    # transaction (which would also drop its transaction-local tenant scope).
    try:
        async with session.begin_nested():
            session.add(raid)
        return raid
    except IntegrityError:
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


async def list_tracked_raids(
    session: AsyncSession, *, tenant_id: uuid.UUID, limit: int | None = None
) -> list[TrackedRaid]:
    """Most recently asked-about raids first; ``limit`` bounds the read (PERF-013)."""
    stmt = (
        select(TrackedRaid)
        .where(TrackedRaid.tenant_id == tenant_id)
        .order_by(TrackedRaid.last_asked_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
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


# --- Recent raids (feature 013) ------------------------------------------------


def _insert(session: AsyncSession, model):
    """A dialect ``INSERT`` that supports ``on_conflict_do_nothing`` (Postgres or SQLite)."""
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


def _own_character_link():
    """Links whose character still exists as an own character (FR-016)."""
    return select(RecentRaidCharacter.raid_id).join(
        UserCharacter,
        (UserCharacter.id == RecentRaidCharacter.character_id) & (UserCharacter.role == "self"),
    )


async def list_recent_raids(
    session: AsyncSession, *, tenant_id: uuid.UUID, limit: int
) -> list[tuple[RecentRaid, list[UserCharacter]]]:
    """Newest raids first, each with the own characters that took part (two queries).

    Only ``is_raid`` rows with at least one link to an existing own character are listed.
    """
    linked = _own_character_link().where(RecentRaidCharacter.tenant_id == tenant_id)
    raids = list(
        (
            await session.execute(
                select(RecentRaid)
                .where(
                    RecentRaid.tenant_id == tenant_id,
                    RecentRaid.is_raid.is_(True),
                    RecentRaid.id.in_(linked),
                )
                .order_by(RecentRaid.started_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    if not raids:
        return []
    rows = await session.execute(
        select(RecentRaidCharacter.raid_id, UserCharacter)
        .join(UserCharacter, UserCharacter.id == RecentRaidCharacter.character_id)
        .where(
            RecentRaidCharacter.tenant_id == tenant_id,
            RecentRaidCharacter.raid_id.in_([r.id for r in raids]),
            UserCharacter.role == "self",
        )
        .order_by(UserCharacter.created_at, UserCharacter.name)
    )
    chars: dict[uuid.UUID, list[UserCharacter]] = {}
    for raid_id, char in rows:
        chars.setdefault(raid_id, []).append(char)
    return [(r, chars.get(r.id, [])) for r in raids]


async def upsert_listed_reports(
    session: AsyncSession, *, tenant_id: uuid.UUID, reports: list[ListedReport]
) -> list[str]:
    """Store reports from the list step and link their characters; return codes needing details.

    New codes are inserted; rows that aren't final get the latest ``ended_at``/title/zone/guild
    (a live log keeps growing). Final rows are left alone (FR-012). Race-safe: inserts and
    links use ``ON CONFLICT DO NOTHING``.
    """
    if not reports:
        return []
    merged: dict[str, ListedReport] = {}
    for r in reports:  # one entry per code; links are the union
        prev = merged.get(r.code)
        merged[r.code] = (
            r if prev is None else replace(r, character_ids=prev.character_ids | r.character_ids)
        )
    reports = list(merged.values())
    codes = list(merged)
    existing = {
        row.report_code: row
        for row in (
            await session.execute(
                select(RecentRaid).where(
                    RecentRaid.tenant_id == tenant_id, RecentRaid.report_code.in_(codes)
                )
            )
        ).scalars()
    }
    new = [r for r in reports if r.code not in existing]
    if new:
        await session.execute(
            _insert(session, RecentRaid)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_id,
                        "report_code": r.code,
                        "title": r.title[:200],
                        "zone_id": r.zone_id,
                        "zone_name": r.zone_name,
                        "guild_name": r.guild_name,
                        "started_at": r.started_at,
                        "ended_at": r.ended_at,
                        "is_raid": r.is_raid,
                        "is_final": False,
                    }
                    for r in new
                ]
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "report_code"])
        )
    for r in reports:
        row = existing.get(r.code)
        if row is not None and not row.is_final:
            row.title = r.title[:200]
            row.zone_id, row.zone_name, row.guild_name = r.zone_id, r.zone_name, r.guild_name
            row.ended_at = r.ended_at
            row.is_raid = row.is_raid or r.is_raid
    await session.flush()

    ids = dict(
        (
            await session.execute(
                select(RecentRaid.report_code, RecentRaid.id).where(
                    RecentRaid.tenant_id == tenant_id, RecentRaid.report_code.in_(codes)
                )
            )
        ).all()
    )
    # Only link characters that still exist (one may be removed mid-refresh).
    wanted = {c for r in reports for c in r.character_ids}
    live = set(
        (
            await session.execute(
                select(UserCharacter.id).where(
                    UserCharacter.tenant_id == tenant_id,
                    UserCharacter.role == "self",
                    UserCharacter.id.in_(wanted),
                )
            )
        ).scalars()
    )
    links = [
        {"raid_id": ids[r.code], "character_id": c, "tenant_id": tenant_id}
        for r in reports
        if r.code in ids
        for c in r.character_ids
        if c in live
    ]
    if links:
        await session.execute(
            _insert(session, RecentRaidCharacter)
            .values(links)
            .on_conflict_do_nothing(index_elements=["raid_id", "character_id"])
        )
    return [r.code for r in reports if r.code not in existing or not existing[r.code].is_final]


async def set_report_details(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    code: str,
    details: ReportDetails,
    final_before: datetime,
) -> None:
    """Record the detail step's findings; a report that ended before ``final_before`` is final."""
    await session.execute(
        update(RecentRaid)
        .where(RecentRaid.tenant_id == tenant_id, RecentRaid.report_code == code)
        .values(
            ended_at=details.ended_at,
            difficulty=details.difficulty,
            bosses_pulled=details.bosses_pulled,
            bosses_killed=details.bosses_killed,
            is_raid=details.is_raid,
            is_final=details.ended_at < final_before,
            details_fetched_at=datetime.now(timezone.utc),
        )
        .execution_options(synchronize_session=False)
    )


async def get_recent_raid(
    session: AsyncSession, report_code: str, *, tenant_id: uuid.UUID
) -> RecentRaid | None:
    result = await session.execute(
        select(RecentRaid).where(
            RecentRaid.tenant_id == tenant_id, RecentRaid.report_code == report_code
        )
    )
    return result.scalar_one_or_none()


async def get_refresh(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> RecentRaidRefresh | None:
    result = await session.execute(
        select(RecentRaidRefresh).where(RecentRaidRefresh.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def claim_refresh(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    character_set: str,
    force: bool,
    min_gap_s: int,
    stale_s: int,
) -> uuid.UUID | None:
    """Atomically claim this tenant's refresh; return the new ``run_id``, or ``None``.

    One conditional ``UPDATE … RETURNING`` is the lock across instances (research R4). The
    gate (data-model §3): a stale ``running`` claim (older than ``stale_s``) is always taken
    over; otherwise not running, and one of: never finished, finished over ``min_gap_s``
    ago, the own-character set changed, or ``force`` after a failure.
    """
    now = datetime.now(timezone.utc)
    await session.execute(
        _insert(session, RecentRaidRefresh)
        .values(tenant_id=tenant_id, status="idle")
        .on_conflict_do_nothing(index_elements=["tenant_id"])
    )
    R = RecentRaidRefresh
    # A run that never recorded an outcome (crash, restart, throttled instance) is taken
    # over once stale, whatever the gap since the previous run finished (FR-026).
    stale = (R.status == "running") & (R.started_at < now - timedelta(seconds=stale_s))
    due = [
        R.finished_at.is_(None),
        R.finished_at < now - timedelta(seconds=min_gap_s),
        R.character_set.is_(None),
        R.character_set != character_set,
    ]
    if force:
        due.append(R.status == "failed")
    run_id = uuid.uuid4()
    result = await session.execute(
        update(R)
        .where(R.tenant_id == tenant_id, or_(stale, (R.status != "running") & or_(*due)))
        .values(status="running", run_id=run_id, started_at=now, character_set=character_set)
        .returning(R.run_id)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one_or_none()


async def finish_refresh(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    ok: bool,
    error: str | None,
) -> None:
    """Record a run's outcome. A run whose claim was taken over (stale ``run_id``) is a no-op."""
    now = datetime.now(timezone.utc)
    values: dict = {
        "status": "succeeded" if ok else "failed",
        "finished_at": now,
        "last_error": None if ok else error,
    }
    if ok:
        values["last_success_at"] = now
    await session.execute(
        update(RecentRaidRefresh)
        .where(RecentRaidRefresh.tenant_id == tenant_id, RecentRaidRefresh.run_id == run_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


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


# Feature 012: a tenant may register several characters as its own (``role == "self"``).
# The limit lives here only; the API exposes it as ``ProfileOut.own_limit``.
MAX_OWN_CHARACTERS = 10


class CharacterConflict(Exception):
    """A character add was refused. ``code`` is the API ``detail``: ``duplicate_character``,
    ``duplicate_friend``, ``already_friend``, ``already_own`` or ``character_limit``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def find_character_identity(
    session: AsyncSession, *, tenant_id: uuid.UUID, name: str, server: str, region: str
) -> UserCharacter | None:
    """Return the tenant's character with this identity in either role (case-insensitive)."""
    result = await session.execute(
        select(UserCharacter).where(
            UserCharacter.tenant_id == tenant_id,
            func.lower(UserCharacter.name) == name.lower(),
            func.lower(UserCharacter.server) == server.lower(),
            func.lower(UserCharacter.region) == region.lower(),
        )
    )
    return result.scalars().first()


async def list_own_characters(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[UserCharacter]:
    result = await session.execute(
        select(UserCharacter)
        .where(UserCharacter.tenant_id == tenant_id, UserCharacter.role == "self")
        .order_by(UserCharacter.created_at)
    )
    return list(result.scalars().all())


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
) -> tuple[list[UserCharacter], list[UserCharacter], GuildProfile | None]:
    """Return the tenant's profile: (own characters, friends, guild)."""
    return (
        await list_own_characters(session, tenant_id=tenant_id),
        await list_friend_characters(session, tenant_id=tenant_id),
        await get_guild_profile(session, tenant_id=tenant_id),
    )


async def add_character(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role: str,
    name: str,
    server: str,
    region: str,
    raid_role: str | None = None,
) -> UserCharacter:
    """Add an own (``role="self"``) or friend character.

    Raises ``CharacterConflict`` when the identity is already saved in either role, or when
    the own-character limit is reached. ``IntegrityError`` remains the backstop for a
    same-role race on the DB unique constraint.
    """
    existing = await find_character_identity(
        session, tenant_id=tenant_id, name=name, server=server, region=region
    )
    if existing is not None:
        if existing.role == role:
            raise CharacterConflict(
                "duplicate_character" if role == "self" else "duplicate_friend"
            )
        raise CharacterConflict("already_friend" if role == "self" else "already_own")
    if role == "self":
        count = await session.scalar(
            select(func.count())
            .select_from(UserCharacter)
            .where(UserCharacter.tenant_id == tenant_id, UserCharacter.role == "self")
        )
        if (count or 0) >= MAX_OWN_CHARACTERS:
            raise CharacterConflict("character_limit")
    char = UserCharacter(
        tenant_id=tenant_id,
        role=role,
        name=name,
        server=server,
        region=region,
        raid_role=raid_role,
    )
    session.add(char)
    await session.flush()
    return char


async def update_character_role(
    session: AsyncSession,
    char_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID,
    role: str,
    raid_role: str | None,
) -> UserCharacter | None:
    """Set a character's raid-role override in place (US4 / FR-028). ``None`` clears it.

    Returns the updated character, or ``None`` when the id is not a ``role`` character of
    this tenant (the caller maps that to 404). Never creates a new row.
    """
    result = await session.execute(
        select(UserCharacter).where(
            UserCharacter.id == char_id,
            UserCharacter.tenant_id == tenant_id,
            UserCharacter.role == role,
        )
    )
    char = result.scalar_one_or_none()
    if char is None:
        return None
    char.raid_role = raid_role
    await session.flush()
    return char


async def delete_character(
    session: AsyncSession, char_id: uuid.UUID, *, tenant_id: uuid.UUID, role: str
) -> bool:
    result = await session.execute(
        delete(UserCharacter).where(
            UserCharacter.id == char_id,
            UserCharacter.tenant_id == tenant_id,
            UserCharacter.role == role,
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


async def set_character_spec(
    session: AsyncSession,
    char_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID,
    class_name: str | None,
    active_spec: str | None,
) -> UserCharacter | None:
    """Persist a character's resolved ``(class_name, active_spec)`` (feature 008 / US3).

    The guide itself lives in the shared ``spec_guides`` library keyed by this pair; the
    character no longer stores guide content/status (those columns were dropped by 0008).
    """
    char = await get_character(session, char_id, tenant_id=tenant_id)
    if char is None:
        return None
    char.class_name = class_name
    char.active_spec = active_spec
    await session.flush()
    return char


# --- Spec guides (features 008, 015) — GLOBAL, non-tenant shared library -------
# These helpers take a plain (non-tenant) session: ``spec_guides`` has no ``tenant_id``
# and no RLS (plan Complexity Tracking). Keyed by the WCL ``(class_name, spec)`` pair plus
# the feature-015 ``content_type`` (``raid`` | ``mplus``).


async def get_spec_guide(
    session: AsyncSession, *, class_name: str, spec: str, content_type: str = "raid"
) -> SpecGuide | None:
    result = await session.execute(
        select(SpecGuide).where(
            SpecGuide.class_name == class_name,
            SpecGuide.spec == spec,
            SpecGuide.content_type == content_type,
        )
    )
    return result.scalar_one_or_none()


_UNSET: object = object()  # "leave the column unchanged" sentinel (feature 009)


async def upsert_spec_guide(
    session: AsyncSession,
    *,
    class_name: str,
    spec: str,
    status: str,
    content_type: str = "raid",
    guide_markdown: str | None = None,
    game_patch: str | None | object = _UNSET,
    generated_at: datetime | None | object = _UNSET,
    sources: list | None | object = _UNSET,
    major_cooldowns: list | None | object = _UNSET,
    **columns: object,
) -> SpecGuide:
    """Create or update one guide's row. Stamps markdown only when provided.

    The provenance columns (and any feature-015 column passed in ``columns``, e.g.
    ``failure_reason``) are stamped only when passed (``None`` clears them); omitted ⇒
    unchanged, so status flips never touch them.

    Raises ``IntegrityError`` if a concurrent insert wins the unique
    ``(class, spec, content_type)`` constraint — the caller rolls back and re-reads the
    winner (contracts: dedup).
    """
    unknown = set(columns) - _GUIDE_STAMP_COLUMNS
    if unknown:
        raise TypeError(f"unknown spec_guides columns: {sorted(unknown)}")
    stamped = {
        "game_patch": game_patch,
        "generated_at": generated_at,
        "sources": sources,
        "major_cooldowns": major_cooldowns,
        **columns,
    }
    stamped = {column: value for column, value in stamped.items() if value is not _UNSET}
    existing = await get_spec_guide(
        session, class_name=class_name, spec=spec, content_type=content_type
    )
    if existing is not None:
        existing.status = status
        if guide_markdown is not None:
            existing.guide_markdown = guide_markdown
        for column, value in stamped.items():
            setattr(existing, column, value)
        await session.flush()
        return existing
    guide = SpecGuide(
        class_name=class_name,
        spec=spec,
        content_type=content_type,
        status=status,
        guide_markdown=guide_markdown,
        **stamped,
    )
    session.add(guide)
    await session.flush()
    return guide


# Feature-015 columns ``upsert_spec_guide`` may stamp by keyword.
_GUIDE_STAMP_COLUMNS = frozenset(
    {
        "brief",
        "claims",
        "season",
        "briefing",
        "evidence",
        "draft",
        "review_issues",
        "failure_reason",
        "stale_reason",
        "last_wanted_at",
    }
)


async def publish_spec_guide(
    session: AsyncSession,
    *,
    class_name: str,
    spec: str,
    content_type: str,
    markdown: str,
    brief: dict | None,
    claims: list | None,
    game_patch: str | None,
    season: str | None,
    generated_at: datetime,
    sources: list | None,
    major_cooldowns: list | None,
    briefing: dict | None,
    evidence: dict | None,
) -> SpecGuide:
    """Publish a verified run: overwrite every published column at once, mark the row
    ``ready`` and clear the latest-run leftovers (draft, issues, failure, staleness)."""
    return await upsert_spec_guide(
        session,
        class_name=class_name,
        spec=spec,
        content_type=content_type,
        status="ready",
        guide_markdown=markdown,
        game_patch=game_patch,
        generated_at=generated_at,
        sources=sources,
        major_cooldowns=major_cooldowns,
        brief=brief,
        claims=claims,
        season=season,
        briefing=briefing,
        evidence=evidence,
        draft=None,
        review_issues=None,
        failure_reason=None,
        stale_reason=None,
    )


async def hold_spec_guide(
    session: AsyncSession,
    *,
    class_name: str,
    spec: str,
    content_type: str,
    draft: dict,
    review_issues: list,
) -> SpecGuide:
    """Hold a run that did not pass review: store the draft and its open issues as
    ``needs_review``; the published columns stay untouched (FR-049)."""
    return await upsert_spec_guide(
        session,
        class_name=class_name,
        spec=spec,
        content_type=content_type,
        status="needs_review",
        draft=draft,
        review_issues=review_issues,
        failure_reason=None,
    )


async def fail_spec_guide(
    session: AsyncSession,
    *,
    class_name: str,
    spec: str,
    content_type: str,
    reason: str,
    review_issues: list | None | object = _UNSET,
) -> SpecGuide:
    """Mark the latest run ``failed`` with a short machine-readable reason; the published
    columns stay untouched."""
    extra = {} if review_issues is _UNSET else {"review_issues": review_issues}
    return await upsert_spec_guide(
        session,
        class_name=class_name,
        spec=spec,
        content_type=content_type,
        status="failed",
        failure_reason=reason[:200],
        **extra,
    )


# True when a version has ever been published (data-model §2, derived ``has_published``).
_HAS_PUBLISHED = or_(
    SpecGuide.brief.is_not(None), SpecGuide.guide_markdown.is_not(None)
).label("has_published")

# The SpecGuide columns that describe a guide's status, without its text (PERF-014).
_GUIDE_STATUS_COLUMNS = (
    SpecGuide.class_name,
    SpecGuide.spec,
    SpecGuide.content_type,
    SpecGuide.status,
    SpecGuide.updated_at,
    SpecGuide.game_patch,
    SpecGuide.season,
    SpecGuide.generated_at,
    SpecGuide.stale_reason,
    SpecGuide.last_wanted_at,
    SpecGuide.failure_reason,
)


async def list_spec_guides(session: AsyncSession, *, with_text: bool = True) -> list[SpecGuide]:
    """All guide rows (global library). ``with_text=False`` skips the markdown, brief,
    claims and evidence (the roster needs only status columns — PERF-014); each row then
    carries a ``has_published`` attribute computed in SQL."""
    if with_text:
        result = await session.execute(select(SpecGuide))
        return list(result.scalars().all())
    stmt = select(SpecGuide, _HAS_PUBLISHED).options(load_only(*_GUIDE_STATUS_COLUMNS))
    return _with_has_published(await session.execute(stmt))


def _with_has_published(result) -> list[SpecGuide]:
    rows = []
    for guide, has_published in result.all():
        # Not a mapped column: a plain attribute read by the summaries.
        guide.__dict__["has_published"] = bool(has_published)
        rows.append(guide)
    return rows


def guide_has_published(guide: SpecGuide) -> bool:
    """Whether the row holds a published version, from the SQL flag when the text columns
    were not loaded (``with_text=False``), else from the columns themselves."""
    if "has_published" in guide.__dict__:
        return guide.__dict__["has_published"]
    return guide.brief is not None or guide.guide_markdown is not None


async def get_spec_guides_for(
    session: AsyncSession,
    keys: list[tuple[str, str, str]],
    *,
    with_text: bool = True,
    ready_only: bool = False,
) -> dict[tuple[str, str, str], SpecGuide]:
    """Batch-load guides for the given ``(class_name, spec, content_type)`` keys → keyed map.

    Matches the exact keys (not a cross product). ``with_text=False`` loads status columns
    (plus ``has_published``) only; ``ready_only`` filters to ready guides in SQL (PERF-014).
    """
    wanted = sorted({(c, s, t) for c, s, t in keys if c and s and t})
    if not wanted:
        return {}
    match = tuple_(SpecGuide.class_name, SpecGuide.spec, SpecGuide.content_type).in_(wanted)
    if with_text:
        stmt = select(SpecGuide).where(match)
        if ready_only:
            stmt = stmt.where(SpecGuide.status == "ready")
        rows = list((await session.execute(stmt)).scalars().all())
    else:
        stmt = select(SpecGuide, _HAS_PUBLISHED).where(match).options(
            load_only(*_GUIDE_STATUS_COLUMNS)
        )
        if ready_only:
            stmt = stmt.where(SpecGuide.status == "ready")
        rows = _with_has_published(await session.execute(stmt))
    return {(g.class_name, g.spec, g.content_type): g for g in rows}


async def set_guide_stale(
    session: AsyncSession, marks: dict[tuple[str, str, str], str]
) -> None:
    """Set ``stale_reason`` on guide rows (the stale scan, FR-050). Status stays as it is."""
    for (class_name, spec, content_type), reason in marks.items():
        await session.execute(
            update(SpecGuide)
            .where(
                SpecGuide.class_name == class_name,
                SpecGuide.spec == spec,
                SpecGuide.content_type == content_type,
            )
            .values(stale_reason=reason)
        )


async def touch_guides_wanted(
    session: AsyncSession, keys: list[tuple[str, str, str]], when: datetime
) -> None:
    """Stamp ``last_wanted_at`` (the in-use rule, FR-051) on existing guide rows."""
    if not keys:
        return
    await session.execute(
        update(SpecGuide)
        .where(tuple_(SpecGuide.class_name, SpecGuide.spec, SpecGuide.content_type).in_(sorted(set(keys))))
        .values(last_wanted_at=when)
        .execution_options(synchronize_session=False)
    )


# --- Guide inaccuracy reports (feature 015, FR-052) — GLOBAL like spec_guides ------------


async def create_guide_report(
    session: AsyncSession,
    *,
    class_name: str,
    spec: str,
    content_type: str,
    user_id: uuid.UUID,
    note: str,
    guide_generated_at: datetime | None,
) -> GuideInaccuracyReport:
    report = GuideInaccuracyReport(
        class_name=class_name,
        spec=spec,
        content_type=content_type,
        user_id=user_id,
        note=note,
        guide_generated_at=guide_generated_at,
        status="open",
    )
    session.add(report)
    await session.flush()
    await session.refresh(report)
    return report


async def list_open_guide_reports(
    session: AsyncSession, *, class_name: str, spec: str, content_type: str, limit: int = 20
) -> list[GuideInaccuracyReport]:
    result = await session.execute(
        select(GuideInaccuracyReport)
        .where(
            GuideInaccuracyReport.class_name == class_name,
            GuideInaccuracyReport.spec == spec,
            GuideInaccuracyReport.content_type == content_type,
            GuideInaccuracyReport.status == "open",
        )
        .order_by(GuideInaccuracyReport.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def resolve_guide_report(
    session: AsyncSession, report_id: uuid.UUID, *, status: str, outcome_note: str | None, when: datetime
) -> None:
    await session.execute(
        update(GuideInaccuracyReport)
        .where(GuideInaccuracyReport.id == report_id, GuideInaccuracyReport.status == "open")
        .values(status=status, outcome_note=(outcome_note or "")[:300] or None, resolved_at=when)
    )


async def list_guide_reports(
    session: AsyncSession, *, status: str | None = None, limit: int = 200
) -> list[GuideInaccuracyReport]:
    stmt = select(GuideInaccuracyReport).order_by(GuideInaccuracyReport.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(GuideInaccuracyReport.status == status)
    return list((await session.execute(stmt)).scalars().all())


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
