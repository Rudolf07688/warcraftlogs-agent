"""Migration 0012 (feature 019): pinned_at + title_source, upgrade and downgrade.

The rest of the suite builds its schema with ``metadata.create_all``; this test runs the
real 0012 ``upgrade()``/``downgrade()`` through Alembic's ``Operations`` on a SQLite table
shaped like ``conversations`` before 0012, with rows already in it (research R10). The
Postgres up/down/up run is a manual step in quickstart.md.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0012_conversation_pin_title.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0012", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def _columns(conn) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns("conversations")}


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(
            sa.text(
                "CREATE TABLE conversations ("
                " id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL,"
                " title VARCHAR(200), model VARCHAR(100),"
                " created_at TIMESTAMP, updated_at TIMESTAMP)"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO conversations (id, tenant_id, title, model) VALUES"
                " ('c1', 't1', 'Raid: Liberation of Undermine', 'm'),"
                " ('c2', 't1', 'how did we do last night', 'm')"
            )
        )
        yield c
    engine.dispose()


def test_revision_chains_after_0011():
    migration = _load_migration()
    assert migration.revision == "0012_conversation_pin_title"
    assert migration.down_revision == "0011_guide_content_types"


def test_upgrade_backfills_existing_rows_as_legacy_and_new_rows_default_auto(conn):
    _run(conn, _load_migration().upgrade)

    rows = conn.execute(
        sa.text("SELECT id, title_source, pinned_at FROM conversations ORDER BY id")
    ).all()
    assert rows == [("c1", "legacy", None), ("c2", "legacy", None)]

    conn.execute(
        sa.text("INSERT INTO conversations (id, tenant_id, title, model) VALUES ('c3', 't1', 'New chat', 'm')")
    )
    new = conn.execute(
        sa.text("SELECT title_source, pinned_at FROM conversations WHERE id = 'c3'")
    ).one()
    assert new == ("auto", None)


def test_downgrade_drops_both_columns_and_keeps_rows(conn):
    migration = _load_migration()
    _run(conn, migration.upgrade)
    conn.execute(sa.text("UPDATE conversations SET pinned_at = CURRENT_TIMESTAMP WHERE id = 'c1'"))

    _run(conn, migration.downgrade)

    assert _columns(conn) == {"id", "tenant_id", "title", "model", "created_at", "updated_at"}
    titles = conn.execute(sa.text("SELECT id, title FROM conversations ORDER BY id")).all()
    assert titles == [("c1", "Raid: Liberation of Undermine"), ("c2", "how did we do last night")]
