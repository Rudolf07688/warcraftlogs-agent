"""spec_guides — global shared spec-guide library (feature 008 / US2)

Creates the GLOBAL ``spec_guides`` table (one guide per ``(class, spec)``), shared across
all tenants. Deliberately **not** tenant-scoped and **no RLS** (plan Complexity Tracking):
guides are generic class/spec advice, not user data. The runtime role is granted DML
(mirroring ``0004_rls``'s default-privilege grants).

Backfills one row per distinct ``(class_name, active_spec)`` from existing ``user_characters``
that already have a ``ready`` guide (most-recent markdown per spec, deduped), so no
user-visible guide content is lost (FR-018). **Keeps** the per-character guide columns so the
old read-path still works until ``0008`` drops them (US3) — the migration split keeps US2
independently deliverable.

Revision ID: 0007_spec_guides
Revises: 0006_raid_role
Create Date: 2026-10-04
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_spec_guides"
down_revision: Union[str, None] = "0006_raid_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def upgrade() -> None:
    op.create_table(
        "spec_guides",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("class_name", sa.String(40), nullable=False),
        sa.Column("spec", sa.String(40), nullable=False),
        sa.Column("guide_markdown", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("created_at", _TS, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, server_default=sa.func.now()),
        sa.UniqueConstraint("class_name", "spec", name="uq_spec_guide_identity"),
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # RLS/grants are Postgres-only; alembic is only ever run against Postgres here
        # (tests build the schema via metadata.create_all), so the backfill is too.
        return

    # The library is GLOBAL: no RLS, but the runtime role still needs DML on it.
    role = _runtime_role()
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON spec_guides TO {role}")

    # Backfill: one row per distinct (class_name, active_spec) that already has a ready
    # per-character guide, taking the most-recently-updated markdown per spec (dedup).
    op.execute(
        """
        INSERT INTO spec_guides (id, class_name, spec, guide_markdown, status,
                                 created_at, updated_at)
        SELECT DISTINCT ON (class_name, active_spec)
               gen_random_uuid(), class_name, active_spec, guide_markdown, 'ready',
               now(), now()
        FROM user_characters
        WHERE guide_status = 'ready'
          AND guide_markdown IS NOT NULL
          AND class_name IS NOT NULL
          AND active_spec IS NOT NULL
        ORDER BY class_name, active_spec, guide_updated_at DESC NULLS LAST
        ON CONFLICT (class_name, spec) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("spec_guides")
