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

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
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
    __table_args__ = (UniqueConstraint("conversation_id", "seq", name="uq_message_conv_seq"),)

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
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

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    report_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
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


class CapturedGraph(Base):
    """Graph JSON the agent fetched during a conversation, kept for PDF rendering (US5)."""

    __tablename__ = "captured_graphs"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
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
        UniqueConstraint("name", "server", "region", "role", name="uq_user_char_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(10))  # "self" | "friend"
    name: Mapped[str] = mapped_column(String(100))
    server: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(8))
    class_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active_spec: Mapped[str | None] = mapped_column(String(40), nullable=True)
    guide_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "none" | "pending" | "ready" | "failed"
    guide_status: Mapped[str] = mapped_column(String(10), server_default="none", default="none")
    guide_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GuildProfile(Base):
    """The single main guild in the global profile (one-main-guild limit, FR-003).

    Singleton row — ``set_guild`` replaces it so a new main guild supersedes the old.
    """

    __tablename__ = "guild_profile"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
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


class Artifact(Base):
    """An agent-declared chart (chart spec), persisted so it re-renders on reload (FR-011)
    and prints in the PDF (FR-024). Mirrors ``CapturedGraph``'s conversation linkage."""

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # "line" | "bar" | "scatter" | "area"
    title: Mapped[str] = mapped_column(String(200))
    spec_json: Mapped[dict] = mapped_column(_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
