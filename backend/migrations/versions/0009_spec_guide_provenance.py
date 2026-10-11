"""spec guide provenance: patch, generated date, sources, major cooldowns (feature 009 / US5)

Adds four nullable columns to the GLOBAL ``spec_guides`` library so a guide carries the
patch it targets, when it was generated, the web sources used, and a machine-readable
list of the spec's major cooldowns (consumed by the ``get_cooldown_usage`` tool via the
in-process registry). No backfill: pre-existing rows keep NULLs and are treated as
"unknown" freshness until regenerated (FR-027).

Revision ID: 0009_guide_provenance
Revises: 0008_drop_guide_columns
Create Date: 2026-10-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# NOTE: revision ids must fit alembic_version.version_num (varchar(32)).
revision: str = "0009_guide_provenance"
down_revision: Union[str, None] = "0008_drop_guide_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("spec_guides", sa.Column("game_patch", sa.String(20), nullable=True))
    op.add_column(
        "spec_guides",
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("spec_guides", sa.Column("sources", _JSON, nullable=True))
    op.add_column("spec_guides", sa.Column("major_cooldowns", _JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("spec_guides", "major_cooldowns")
    op.drop_column("spec_guides", "sources")
    op.drop_column("spec_guides", "generated_at")
    op.drop_column("spec_guides", "game_patch")
