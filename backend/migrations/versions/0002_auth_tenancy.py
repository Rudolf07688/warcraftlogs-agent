"""auth & tenancy: users, tenants, memberships, invitations, sessions, reset tokens, audit

Adds the seven new auth/tenant tables (feature 006). Email columns use ``citext`` so
identity is case-insensitive at the database. Only sha256 digests of raw tokens are
stored (never the raw token). Does NOT yet touch the existing app tables — ``tenant_id``
is added in 0003 after the founder is bootstrapped.

Revision ID: 0002_auth_tenancy
Revises: 0001_baseline
Create Date: 2026-10-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, JSONB

revision: str = "0002_auth_tenancy"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_EMAIL = CITEXT().with_variant(sa.String(320), "sqlite")
_JSONB = JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("email", _EMAIL, nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="invited"),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("password_changed_at", _TS, nullable=True),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("login_blocked_until", _TS, nullable=True),
        sa.Column("last_login_at", _TS, nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('invited', 'active', 'disabled')", name="ck_user_status"),
        sa.CheckConstraint(
            "status <> 'active' OR password_hash IS NOT NULL", name="ck_user_active_has_hash"
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "tenants",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("created_at", _TS, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_tenant_status"),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column(
            "tenant_id", _UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("role", sa.String(16), nullable=False, server_default="tenant_admin"),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("created_at", _TS, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('tenant_admin', 'member')", name="ck_membership_role"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_membership_status"),
    )

    op.create_table(
        "invitations",
        sa.Column("id", _UUID, primary_key=True),
        # NULL until acceptance auto-provisions the workspace (v1 one-per-user).
        sa.Column(
            "tenant_id", _UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("email", _EMAIL, nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="tenant_admin"),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("accepted_at", _TS, nullable=True),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.Column("invited_by", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_invitation_token_hash"),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])
    op.create_index("ix_invitations_email", "invitations", ["email"])
    # At most one OPEN invitation per email (v1 one-workspace-per-user).
    op.create_index(
        "uq_open_invitation",
        "invitations",
        ["email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    # NOTE: table is `auth_sessions`, not `sessions` — ADK's DatabaseSessionService
    # owns a `sessions` table in the same database.
    op.create_table(
        "auth_sessions",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        # CSRF token is HMAC-derived from the session id (not stored).
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "active_tenant_id",
            _UUID,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", _TS, server_default=sa.func.now()),
        sa.Column("last_seen_at", _TS, server_default=sa.func.now()),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.Column("user_agent_hash", sa.LargeBinary(32), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_auth_session_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index(
        "ix_auth_sessions_user_active",
        "auth_sessions",
        ["user_id", "expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("consumed_at", _TS, nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_reset_token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "auth_audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", _TS, server_default=sa.func.now()),
        sa.Column("actor_user_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_user_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tenant_id", _UUID, sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("metadata", _JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint("outcome IN ('success', 'failure')", name="ck_audit_outcome"),
    )
    op.create_index("ix_auth_audit_events_occurred_at", "auth_audit_events", ["occurred_at"])
    op.create_index("ix_auth_audit_events_event_type", "auth_audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("auth_audit_events")
    op.drop_table("password_reset_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("invitations")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
    op.drop_table("users")
