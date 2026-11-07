---
id: bootstrap-admin-pins-auth-tables
anchors: [sym:backend/cli/bootstrap_admin.py::bootstrap_admin, file:backend/migrations/versions/]
by: dev-5 Edda
verified: 245b3db 2026-11-07
---
bootstrap_admin runs between 'alembic upgrade 0002_auth_tenancy' and 'upgrade head' with today's
ORM models (pg.py up does the same). The ORM INSERT names every mapped column, so a new mapped
column on users, tenants, tenant_memberships or auth_audit_events breaks first-admin setup. Put
new per-tenant or per-user data in its own table (as 074's profile_settings) instead.
