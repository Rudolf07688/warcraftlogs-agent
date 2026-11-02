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

# Index rule (051 sc-359): on an existing table, create and drop indexes CONCURRENTLY outside the
# migration transaction, so the build never blocks the app's writes:
#     with op.get_context().autocommit_block():
#         op.drop_index("ix_name", table_name="t", postgresql_concurrently=True, if_exists=True)
#         op.create_index("ix_name", "t", ["col"], postgresql_concurrently=True)
# The drop first clears an INVALID index a failed build left behind. Put data changes (backfills)
# before the block: it commits the migration transaction so far. See 0020 and 0021.


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
