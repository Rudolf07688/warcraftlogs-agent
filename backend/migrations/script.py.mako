"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

# Lock rule (051 sc-359): on an existing, busy table, never hold a lock for longer than one short
# statement. Run the work outside the migration transaction, every step guarded so a re-run
# after a failure converges:
#     with op.get_context().autocommit_block():
#         op.add_column("t", sa.Column("c", sa.Boolean(), nullable=False, server_default=sa.false()),
#                       if_not_exists=True)  # constant default: metadata only, a brief lock
#         ...backfill in short batches (each statement commits on its own here)...
#         op.drop_index("ix_name", table_name="t", postgresql_concurrently=True, if_exists=True)
#         op.create_index("ix_name", "t", ["col"], postgresql_concurrently=True)
# The drop first clears an INVALID index a failed build left behind. See 0020 and 0021.


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
