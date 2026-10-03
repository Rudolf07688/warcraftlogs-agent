"""Alembic migration environment (async engine, migration-owner role).

Schema authority for the backend from feature 006 onward. Runs under the
**migration-owner** DB role (``settings.owner_database_url``) — distinct from the
non-privileged runtime role the app uses — so it can ALTER tables and enable RLS
(research R1/R4).

``target_metadata`` is the app's ``Base.metadata``. ADK's own ``DatabaseSessionService``
tables are created by ADK (``prepare_tables()``), are not part of our ORM models, and
are therefore intentionally excluded from autogenerate.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from backend.app.config import settings
from backend.app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the owner URL from app settings (keeps credentials out of alembic.ini).
config.set_main_option("sqlalchemy.url", settings.owner_database_url)

target_metadata = Base.metadata

# ADK-managed tables (created by DatabaseSessionService.prepare_tables) live in the same
# database but outside our ORM models; never let autogenerate try to drop them. Our auth
# session table is deliberately named `auth_sessions` to avoid colliding with ADK's
# `sessions`.
_ADK_TABLES = {"sessions", "events", "app_states", "user_states"}


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table" and name in _ADK_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.owner_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
