"""drop retired per-character guide columns (feature 008 / US3)

Removes ``user_characters.guide_markdown / guide_status / guide_updated_at``. A character's
guide now lives in the GLOBAL ``spec_guides`` library (created + backfilled by ``0007``),
keyed by the character's resolved ``(class_name, active_spec)``; its status is derived at read
time (``CharacterOut``) and injected into the agent preamble by spec (feature 008 / US3).

Sequenced AFTER the read-path refactor (``CharacterOut`` derived status, ``build_preamble``
by-spec, ``run_character_guide`` → ``ensure_spec_guide``) so the app never reads a dropped
column. Downgrade re-adds the three columns as nullable (backfilled content is not restored
to characters — a documented one-way data move; the shared library retains it).

Revision ID: 0008_drop_guide_columns
Revises: 0007_spec_guides
Create Date: 2026-10-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# NOTE: revision ids must fit alembic_version.version_num (varchar(32)); keep this short
# even though the filename is descriptive.
revision: str = "0008_drop_guide_columns"
down_revision: Union[str, None] = "0007_spec_guides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.drop_column("user_characters", "guide_updated_at")
    op.drop_column("user_characters", "guide_status")
    op.drop_column("user_characters", "guide_markdown")


def downgrade() -> None:
    op.add_column(
        "user_characters",
        sa.Column("guide_markdown", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_characters",
        sa.Column(
            "guide_status",
            sa.String(10),
            nullable=True,
            server_default="none",
        ),
    )
    op.add_column(
        "user_characters",
        sa.Column("guide_updated_at", _TS, nullable=True),
    )
