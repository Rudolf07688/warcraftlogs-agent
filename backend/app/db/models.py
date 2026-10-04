"""SQLAlchemy ORM models for app state (conversations + messages)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# JSONB on PostgreSQL, plain JSON on SQLite (so the same model backs tests too).
_JSON = JSON().with_variant(JSONB(), "postgresql")

# Generic UUID type: renders as native ``uuid`` on PostgreSQL and ``CHAR(32)`` on
# SQLite, so the same models back both production (Postgres) and fast unit tests.
_UUID = Uuid(as_uuid=True)


class Base(DeclarativeBase):
    pass


# =============================================================================
# Auth / tenancy (feature 006 multi-tenancy) — see specs/006-multi-tenancy/data-model.md
#
# Email is stored as a plain string here (normalized to lowercase by the app for a
# case-insensitive identity); the Postgres migration promotes the column to `citext`
# so uniqueness is case-insensitive at the DB too. Token digests are raw sha256 bytes
# (never the raw token). All timestamps are timezone-aware. These models are portable
# to SQLite for tests; Postgres-only RLS is applied by migration 0004_rls.
# =============================================================================


class User(Base):
    """Global identity. One row per person; email is the natural login key."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('invited', 'active', 'disabled')", name="ck_user_status"
        ),
        # An active account MUST have a password hash set (activation sets both).
        CheckConstraint(
            "status <> 'active' OR password_hash IS NOT NULL",
            name="ck_user_active_has_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), server_default="invited", default="invited"
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, server_default=false(), default=False
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, server_default="0", default=0
    )
    login_blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Tenant(Base):
    """A private workspace. In v1 exactly one per user (auto-provisioned on accept)."""

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="ck_tenant_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(10), server_default="active", default="active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantMembership(Base):
    """user ↔ tenant link. v1: one per user, as the workspace owner (tenant_admin)."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('tenant_admin', 'member')", name="ck_membership_role"
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')", name="ck_membership_status"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), server_default="tenant_admin", default="tenant_admin")
    status: Mapped[str] = mapped_column(String(10), server_default="active", default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Invitation(Base):
    """Single-use invite. Only the sha256 of the raw token is stored."""

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('tenant_admin', 'member')", name="ck_invitation_role"
        ),
        # At most one OPEN invitation per email. v1 is one-workspace-per-user and the
        # workspace is created at acceptance, so the invite is keyed by email alone
        # (tenant_id is NULL until accepted). Accepted/revoked rows are excluded so
        # re-inviting the same person later is possible.
        Index(
            "uq_open_invitation",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
            sqlite_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    # NULL until acceptance auto-provisions the workspace (v1 one-per-user).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(16), server_default="tenant_admin", default="tenant_admin")
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    """Opaque server-side session. Only sha256 digests of the raw tokens are stored.

    Table is ``auth_sessions`` (NOT ``sessions``) because Google ADK's
    ``DatabaseSessionService`` owns a table named ``sessions`` in the same database.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index(
            "ix_auth_sessions_user_active",
            "user_id",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    # No stored CSRF digest: the CSRF token is HMAC-derived from the session id (auth/csrf.py).
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    active_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)


class PasswordResetToken(Base):
    """Single-use password reset. Only the sha256 of the raw token is stored."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthAuditEvent(Base):
    """Append-only security audit log. NEVER stores passwords, hashes, or raw tokens."""

    __tablename__ = "auth_audit_events"
    __table_args__ = (
        CheckConstraint("outcome IN ('success', 'failure')", name="ck_audit_outcome"),
    )

    # BigInteger on Postgres; Integer on SQLite so the rowid autoincrements in tests
    # (SQLite only auto-increments an INTEGER PRIMARY KEY, not BIGINT).
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(10))
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", _JSON, server_default="{}", default=dict
    )


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_tenant_updated", "tenant_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    # feature 006: owning workspace. Denormalized onto every tenant-owned table so one RLS
    # predicate (tenant_id = app.tenant_id) applies uniformly; always set from the parent.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.seq",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_message_conv_seq"),
        Index("ix_messages_tenant_conv_seq", "tenant_id", "conversation_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(10))  # "user" | "agent"
    content: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    # "complete" | "partial" — set to "partial" when a streamed agent reply is
    # interrupted (US2 / FR-009), so the UI/PDF can flag unfinished answers.
    status: Mapped[str] = mapped_column(String(10), server_default="complete", default="complete")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class TrackedRaid(Base):
    """A Warcraft Logs report the user has successfully pulled data for (US1).

    Keyed by ``report_code`` (natural dedup key) and standalone — it outlives any
    single conversation, so a deleted chat only nulls ``last_conversation_id``.
    """

    __tablename__ = "tracked_raids"
    __table_args__ = (
        # report_code uniqueness is now per-tenant (feature 006).
        UniqueConstraint("tenant_id", "report_code", name="uq_tracked_raid_tenant_code"),
        Index("ix_tracked_raids_tenant_asked", "tenant_id", "last_asked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    report_code: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(200))
    zone: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guild: Mapped[str | None] = mapped_column(String(120), nullable=True)
    report_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # US2/US4: deduped distinct boss list for this report (list of
    # {encounter_id, name, difficulty, kill}); merged on each get_report_fights.
    encounters: Mapped[list | None] = mapped_column(_JSON, nullable=True)


class KnownPlayer(Base):
    """A WoW character discovered via successful tool results (feature 007 / US1).

    Distinct from a profile ``UserCharacter`` — these are players the user has looked
    up (character rankings), captured silently so later conversations can resolve a
    bare name → server/region without re-asking. Identity is ``(name, server, region)``.
    """

    __tablename__ = "known_players"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", "server", "region", name="uq_known_player_identity"
        ),
        Index("ix_known_players_tenant_seen", "tenant_id", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100))
    server: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(8))
    class_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # provenance
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnownEncounter(Base):
    """A raid zone/boss the user has queried or resolved (feature 007 / US1).

    Captured primarily from ``find_encounter`` matches, independent of any report, so
    later conversations can disambiguate a boss name without re-resolving it. Dedup
    key is ``(tenant_id, encounter_id)``.
    """

    __tablename__ = "known_encounters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "encounter_id", name="uq_known_encounter_identity"),
        Index("ix_known_encounters_tenant_seen", "tenant_id", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[int] = mapped_column(Integer)
    encounter_name: Mapped[str] = mapped_column(String(120))
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zone_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CapturedGraph(Base):
    """Graph JSON the agent fetched during a conversation, kept for PDF rendering (US5)."""

    __tablename__ = "captured_graphs"
    __table_args__ = (Index("ix_captured_graphs_tenant_conv", "tenant_id", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_code: Mapped[str] = mapped_column(String(32))
    data_type: Mapped[str] = mapped_column(String(40))
    fight_id: Mapped[int] = mapped_column(Integer, default=0)
    source_id: Mapped[int] = mapped_column(Integer, default=0)
    graph_json: Mapped[dict] = mapped_column(_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserCharacter(Base):
    """A self or friend character in the single global profile (feature 005 / US1).

    Each character carries a resolved active spec and a persisted spec guide fetched
    by the background guide task (US6). Identity is ``(name, server, region)``.
    """

    __tablename__ = "user_characters"
    __table_args__ = (
        # Identity uniqueness is now per-tenant (feature 006).
        UniqueConstraint(
            "tenant_id", "name", "server", "region", "role", name="uq_user_char_identity"
        ),
        Index("ix_user_characters_tenant_role", "tenant_id", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10))  # "self" | "friend"
    name: Mapped[str] = mapped_column(String(100))
    server: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(8))
    class_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active_spec: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # US4 (feature 007): the user's raid-role override — "tank" | "healer" | "dps" | NULL
    # (unset). Orthogonal to ``role`` (self/friend). Nullable, no backfill; the effective
    # role is computed as ``raid_role or role_for_spec(active_spec)``. Added by 0006_raid_role.
    raid_role: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Feature 008 / US3: the per-character guide columns (guide_markdown / guide_status /
    # guide_updated_at) were dropped by 0008. A character's guide is now the SHARED
    # ``spec_guides`` row for its ``(class_name, active_spec)``; status is derived at read time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GuildProfile(Base):
    """The single main guild in the global profile (one-main-guild limit, FR-003).

    Singleton row — ``set_guild`` replaces it so a new main guild supersedes the old.
    """

    __tablename__ = "guild_profile"
    __table_args__ = (Index("ix_guild_profile_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120))
    server: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(8))
    summary_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "none" | "pending" | "ready" | "failed"
    summary_status: Mapped[str] = mapped_column(String(10), server_default="none", default="none")
    summary_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SpecGuide(Base):
    """One generated guide per ``(class, spec)`` — a GLOBAL, shared library (feature 008 / US2).

    Deliberately **not** tenant-scoped and **no RLS**: guides are generic class/spec advice,
    not user data (plan Complexity Tracking). A single shared store removes the per-character
    duplication of identical content. Absence of a row ⇒ the spec is "not downloaded"; the
    row ``status`` drives the Class Guides list. ``class_name``/``spec`` are the WCL PascalCase
    filter values from ``wcl_agent.constants.CLASS_SPECS``.
    """

    __tablename__ = "spec_guides"
    __table_args__ = (
        UniqueConstraint("class_name", "spec", name="uq_spec_guide_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    class_name: Mapped[str] = mapped_column(String(40))
    spec: Mapped[str] = mapped_column(String(40))
    guide_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "pending" | "ready" | "failed" (a missing row = not-downloaded / "none")
    status: Mapped[str] = mapped_column(String(10), server_default="pending", default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Artifact(Base):
    """An agent-declared chart (chart spec), persisted so it re-renders on reload (FR-011)
    and prints in the PDF (FR-024). Mirrors ``CapturedGraph``'s conversation linkage."""

    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_tenant_conv", "tenant_id", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # "line" | "bar" | "scatter" | "area"
    title: Mapped[str] = mapped_column(String(200))
    spec_json: Mapped[dict] = mapped_column(_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
