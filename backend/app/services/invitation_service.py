"""Invitation lifecycle: create / resend / revoke / accept (feature 006, US1).

Acceptance runs as one transaction (data-model.md §Invitation-acceptance flow): validate
the single-use token, set the first Argon2id password, activate the user, auto-provision
their workspace (tenant + owner membership), create a session, and write the audit trail.
All acceptance failures surface as ONE generic error (no enumeration); only the raw token
leaves the server, once, at create/resend.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import sessions as session_svc
from ..auth import tokens
from ..auth.passwords import PasswordPolicyError, hash_password, validate_password_policy
from ..config import settings
from ..db.models import Invitation, Tenant, User
from ..repositories import audit
from ..repositories import invitations as inv_repo
from ..repositories import tenants as tenants_repo
from ..repositories import users as users_repo


class InvitationConflict(Exception):
    """A create-time conflict (409): disabled user or already a member."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InvitationInvalid(Exception):
    """A generic accept-time failure (400) — never reveals the specific cause."""

    code = "invalid_or_expired_invitation"
    message = "This invitation link is invalid or has expired."


@dataclass(frozen=True)
class CreatedInvitation:
    invitation: Invitation
    raw_token: str


@dataclass(frozen=True)
class AcceptResult:
    user: User
    tenant: Tenant
    session: session_svc.NewSession


async def create_invitation(
    db: AsyncSession, *, email: str, role: str, invited_by: uuid.UUID | None
) -> CreatedInvitation:
    """Create (or re-create) an open invitation for ``email``; returns the raw token once."""
    normalized = users_repo.normalize_email(email)
    user = await users_repo.get_user_by_email(db, normalized)
    if user is not None:
        if user.status == "disabled":
            raise InvitationConflict("user_disabled", "That account is disabled.")
        if await tenants_repo.list_memberships_for_user(db, user.id):
            raise InvitationConflict("membership_exists", "That user already has a workspace.")
    else:
        user = await users_repo.create_user(db, email=normalized, status="invited")

    await inv_repo.revoke_open_invitations_for_email(db, email=normalized)
    raw_token = tokens.generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.invitation_ttl_s)
    invitation = await inv_repo.create_invitation(
        db,
        email=normalized,
        role=role,
        token_hash=tokens.hash_token(raw_token),
        expires_at=expires_at,
        invited_by=invited_by,
    )
    await audit.record_event(
        db,
        event_type="invitation.created",
        actor_user_id=invited_by,
        target_user_id=user.id,
        metadata={"email": normalized, "role": role},
    )
    return CreatedInvitation(invitation=invitation, raw_token=raw_token)


async def resend_invitation(
    db: AsyncSession, *, invitation_id: uuid.UUID, actor_id: uuid.UUID | None
) -> CreatedInvitation:
    """Rotate an open invitation's token + expiry; the prior link stops working."""
    invitation = await inv_repo.get_invitation(db, invitation_id)
    if invitation is None or invitation.accepted_at is not None:
        raise InvitationInvalid()
    raw_token = tokens.generate_token()
    invitation.token_hash = tokens.hash_token(raw_token)
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.invitation_ttl_s)
    invitation.revoked_at = None
    await db.flush()
    await audit.record_event(
        db,
        event_type="invitation.resent",
        actor_user_id=actor_id,
        metadata={"email": invitation.email},
    )
    return CreatedInvitation(invitation=invitation, raw_token=raw_token)


async def revoke_invitation(
    db: AsyncSession, *, invitation_id: uuid.UUID, actor_id: uuid.UUID | None
) -> bool:
    invitation = await inv_repo.get_invitation(db, invitation_id)
    if invitation is None or invitation.accepted_at is not None:
        return False
    await inv_repo.mark_revoked(db, invitation)
    await audit.record_event(
        db,
        event_type="invitation.revoked",
        actor_user_id=actor_id,
        metadata={"email": invitation.email},
    )
    return True


async def accept_invitation(
    db: AsyncSession,
    *,
    raw_token: str,
    password: str,
    password_confirmation: str,
    user_agent: str | None = None,
) -> AcceptResult:
    """Validate the token, set the password, provision the workspace, and sign in."""
    if password != password_confirmation:
        raise PasswordPolicyError("Passwords do not match.")
    validate_password_policy(password)

    invitation = await inv_repo.get_invitation_by_token_hash(
        db, tokens.hash_token(raw_token), for_update=True
    )
    now = datetime.now(timezone.utc)
    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
        or _aware(invitation.expires_at) <= now
    ):
        raise InvitationInvalid()

    user = await users_repo.get_user_by_email(db, invitation.email)
    if user is None or user.status == "disabled":
        raise InvitationInvalid()

    # Hash while holding the row lock: concurrent accepts block, then see accepted_at set.
    pw_hash = await hash_password(password)
    await users_repo.activate_with_password(db, user, password_hash=pw_hash)

    tenant = await _ensure_workspace(db, user, role=invitation.role)

    invitation.tenant_id = tenant.id
    await inv_repo.mark_accepted(db, invitation)
    await inv_repo.revoke_open_invitations_for_email(
        db, email=invitation.email, exclude_id=invitation.id
    )

    new_session = await session_svc.create_session(
        db, user_id=user.id, active_tenant_id=tenant.id, user_agent=user_agent
    )
    await audit.record_event(
        db,
        event_type="invitation.accepted",
        actor_user_id=user.id,
        target_user_id=user.id,
        tenant_id=tenant.id,
    )
    await audit.record_event(
        db,
        event_type="session.created",
        actor_user_id=user.id,
        tenant_id=tenant.id,
    )
    return AcceptResult(user=user, tenant=tenant, session=new_session)


async def _ensure_workspace(db: AsyncSession, user: User, *, role: str) -> Tenant:
    """Return the user's single workspace, creating tenant + owner membership if needed."""
    memberships = await tenants_repo.list_memberships_for_user(db, user.id)
    if memberships:
        return memberships[0][1]
    tenant = await tenants_repo.create_tenant(db, name=user.email)
    await tenants_repo.create_membership(
        db, tenant_id=tenant.id, user_id=user.id, role="tenant_admin"
    )
    return tenant


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
