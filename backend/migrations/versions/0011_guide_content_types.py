"""guides per content type + published/latest-run split + inaccuracy reports (feature 015)

``spec_guides`` (global, no RLS) gains a ``content_type`` dimension (``raid`` | ``mplus``),
so its identity becomes ``(class_name, spec, content_type)``. Existing rows become ``raid``
guides and are marked ``stale_reason='legacy'`` so they stay visible but regenerate
through the new pipeline once in use (FR-055); guides of saved characters' specs are
stamped as in use so that happens without anyone opening them. New columns hold the published coaching
brief and claims, the season, the briefing and evidence snapshot, and the latest run's
draft / issues / failure reason, plus staleness and in-use tracking (data-model §2).

New global table ``guide_inaccuracy_reports`` (data-model §3).

Revision ID: 0011_guide_content_types
Revises: 0010_recent_raids
Create Date: 2026-10-18
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_guide_content_types"
down_revision: Union[str, None] = "0010_recent_raids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_TS = sa.DateTime(timezone=True)
_UUID = sa.Uuid(as_uuid=True)

_JSON_COLUMNS = ["brief", "claims", "briefing", "evidence", "draft", "review_issues"]


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def upgrade() -> None:
    op.add_column(
        "spec_guides",
        sa.Column("content_type", sa.String(8), nullable=False, server_default="raid"),
    )
    op.alter_column(
        "spec_guides", "status", type_=sa.String(14), existing_type=sa.String(10)
    )
    for name in _JSON_COLUMNS:
        op.add_column("spec_guides", sa.Column(name, _JSON, nullable=True))
    op.add_column("spec_guides", sa.Column("season", sa.String(40), nullable=True))
    op.add_column("spec_guides", sa.Column("failure_reason", sa.String(200), nullable=True))
    op.add_column("spec_guides", sa.Column("stale_reason", sa.String(40), nullable=True))
    op.add_column("spec_guides", sa.Column("last_wanted_at", _TS, nullable=True))

    op.drop_constraint("uq_spec_guide_identity", "spec_guides", type_="unique")
    op.create_unique_constraint(
        "uq_spec_guide_identity", "spec_guides", ["class_name", "spec", "content_type"]
    )
    op.execute("UPDATE spec_guides SET stale_reason = 'legacy'")
    if op.get_bind().dialect.name == "postgresql":
        # A saved character's spec is "in use" (FR-051): stamp those legacy guides so the
        # first stale scans regenerate them (a few per scan, most recently wanted first)
        # instead of leaving the agent without verified briefs (QA SPEC-003). Reads every
        # tenant's characters, like the 0007 backfill.
        op.execute(
            """
            UPDATE spec_guides g SET last_wanted_at = now()
            FROM (SELECT DISTINCT class_name, active_spec FROM user_characters
                  WHERE class_name IS NOT NULL AND active_spec IS NOT NULL) c
            WHERE g.class_name = c.class_name AND g.spec = c.active_spec
            """
        )

    op.create_table(
        "guide_inaccuracy_reports",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("class_name", sa.String(40), nullable=False),
        sa.Column("spec", sa.String(40), nullable=False),
        sa.Column("content_type", sa.String(8), nullable=False),
        sa.Column(
            "user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("guide_generated_at", _TS, nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="open"),
        sa.Column("outcome_note", sa.String(300), nullable=True),
        sa.Column("resolved_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_guide_reports_open",
        "guide_inaccuracy_reports",
        ["class_name", "spec", "content_type"],
        postgresql_where=sa.text("status = 'open'"),
    )
    if op.get_bind().dialect.name == "postgresql":
        # Global like spec_guides: no RLS, but the runtime role needs DML on it.
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON guide_inaccuracy_reports TO {_runtime_role()}"
        )


def downgrade() -> None:
    op.drop_index("ix_guide_reports_open", table_name="guide_inaccuracy_reports")
    op.drop_table("guide_inaccuracy_reports")

    # Back to one guide per (class, spec): Mythic+ rows have no place in the old shape.
    op.execute("DELETE FROM spec_guides WHERE content_type <> 'raid'")
    op.drop_constraint("uq_spec_guide_identity", "spec_guides", type_="unique")
    op.create_unique_constraint("uq_spec_guide_identity", "spec_guides", ["class_name", "spec"])

    op.drop_column("spec_guides", "last_wanted_at")
    op.drop_column("spec_guides", "stale_reason")
    op.drop_column("spec_guides", "failure_reason")
    op.drop_column("spec_guides", "season")
    for name in reversed(_JSON_COLUMNS):
        op.drop_column("spec_guides", name)
    # A "needs_review" status does not fit the old width or vocabulary.
    op.execute("UPDATE spec_guides SET status = 'failed' WHERE status = 'needs_review'")
    op.alter_column(
        "spec_guides", "status", type_=sa.String(10), existing_type=sa.String(14)
    )
    op.drop_column("spec_guides", "content_type")
