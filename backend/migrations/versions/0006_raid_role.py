"""user_characters.raid_role (feature 007 / US4)

Adds the optional per-character raid-role override ("tank" | "healer" | "dps" | NULL).
Nullable with no backfill: rows created before this migration read back NULL and show
their inferred-or-unset effective role. Chains after 0005 (linear history; US4 carries
its own schema so it stays independently deliverable).

Revision ID: 0006_raid_role
Revises: 0005_known_entities
Create Date: 2026-10-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_raid_role"
down_revision: Union[str, None] = "0005_known_entities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_characters",
        sa.Column("raid_role", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_characters", "raid_role")
