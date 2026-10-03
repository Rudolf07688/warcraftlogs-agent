"""Tenant + membership row access (feature 006)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Tenant, TenantMembership


async def create_tenant(session: AsyncSession, *, name: str) -> Tenant:
    tenant = Tenant(name=name)
    session.add(tenant)
    await session.flush()
    return tenant


async def get_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.get(Tenant, tenant_id)


async def set_tenant_status(session: AsyncSession, tenant: Tenant, *, status: str) -> Tenant:
    tenant.status = status
    await session.flush()
    return tenant


async def create_membership(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = "tenant_admin",
) -> TenantMembership:
    membership = TenantMembership(tenant_id=tenant_id, user_id=user_id, role=role)
    session.add(membership)
    await session.flush()
    return membership


async def get_membership(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> TenantMembership | None:
    return await session.get(TenantMembership, (tenant_id, user_id))


async def list_memberships_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[TenantMembership, Tenant]]:
    """Active memberships joined to their tenant (for MeOut / admin views)."""
    result = await session.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(TenantMembership.user_id == user_id, TenantMembership.status == "active")
        .order_by(Tenant.created_at)
    )
    return [(m, t) for m, t in result.all()]
