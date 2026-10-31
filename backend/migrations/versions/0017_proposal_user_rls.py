"""user-level RLS on profile_proposals (feature 036, sc-222)

0016 scoped ``profile_proposals`` to the tenant only, although the rule is "same user": user
scoping was application-level. This replaces the tenant policy with one that checks the
tenant **and** the user (``app.user_id``, set by every tenant-scoped transaction). Policies
are OR'ed, so the old one is dropped rather than a second one added. Postgres only.

Revision ID: 0017_proposal_user_rls
Revises: 0016_profile_proposals
Create Date: 2026-10-31
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0017_proposal_user_rls"
down_revision: Union[str, None] = "0016_profile_proposals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "profile_proposals"
_TENANT = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_USER = "user_id = NULLIF(current_setting('app.user_id', true), '')::uuid"


def _policy(name: str, predicate: str) -> str:
    return f"CREATE POLICY {name} ON {_TABLE} USING ({predicate}) WITH CHECK ({predicate})"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # RLS is Postgres-only; SQLite tests assert app-level scoping instead.
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {_TABLE}")
    op.execute(_policy("tenant_user_isolation", f"{_TENANT} AND {_USER}"))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DROP POLICY IF EXISTS tenant_user_isolation ON {_TABLE}")
    op.execute(_policy("tenant_isolation", _TENANT))
