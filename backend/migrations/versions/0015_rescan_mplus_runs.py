"""re-scan recent Mythic+ runs (feature 022 fix)

Before this fix, a key with a known roster but none of the user's characters in it (another
group's key in a shared log) was stored and attributed to every own character in the report.
Those reports are already final, so they would never be examined again. This data-only
revision clears the stored runs and reopens the non-raid reports, so the next welcome
refresh rebuilds the runs with the corrected matching. Nothing else changes.

Revision ID: 0015_rescan_mplus_runs
Revises: 0014_recent_mplus_runs
Create Date: 2026-10-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0015_rescan_mplus_runs"
down_revision: Union[str, None] = "0014_recent_mplus_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATEMENTS = [
    ("recent_mplus_run_characters", "DELETE FROM recent_mplus_run_characters"),
    ("recent_mplus_runs", "DELETE FROM recent_mplus_runs"),
    (
        "recent_raids",
        "UPDATE recent_raids SET is_final = false, details_fetched_at = NULL WHERE NOT is_raid",
    ),
]


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    for table, sql in _STATEMENTS:
        if postgres:
            # These tables FORCE RLS, so a non-superuser owner would match no rows (same as
            # 0012). Lift FORCE around each statement; the revision runs in one transaction,
            # so a failure restores FORCE.
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(sql)
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        else:
            op.execute(sql)


def downgrade() -> None:
    # Data-only: the cleared runs are derived and are rebuilt by the next refresh.
    pass
