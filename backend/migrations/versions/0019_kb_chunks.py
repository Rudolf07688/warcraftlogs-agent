"""knowledge base chunks — pgvector, kb_chunks + kb_chat_chunks (feature 043, sc-111)

Postgres only (the vector and tsvector types exist nowhere else; SQLite tests build the schema
from the models). Needs the ``pgvector/pgvector:pg17-trixie`` image: Alembic runs as the owner role,
which may ``CREATE EXTENSION``; pgvector 0.8+ is required for filtered HNSW scans
(``hnsw.iterative_scan``, feature 044).

* ``kb_chunks`` (global, no RLS, like ``raw_fetches`` and ``spec_guides``): chunks of stored WCL
  fetches (``kind`` ``wcl``, FK ``raw_fetch_id`` → ``raw_fetches.query_key``) and published
  guides (``guide``, FK ``guide_id`` → ``spec_guides.id``), both ``ON DELETE CASCADE``.
* ``kb_chat_chunks`` (tenant, RLS ``tenant_isolation`` enabled and forced, like 0004): one chunk
  per finished exchange. Its conversation is referenced together with the tenant through the
  new ``UNIQUE (id, tenant_id)`` on ``conversations``: FK checks bypass RLS, so this is what
  stops a chunk of tenant B from naming a conversation of tenant A.

Both tables: rendered ``text``, ``content_hash``, nullable ``embedding vector(768)`` (NULL until
embedded), ``embed_model``, ``embedded_at``, a generated ``tsv`` (``simple`` for WCL, ``english``
for guides and chats), typed filters and ``extra jsonb``. See
specs/043-kb-store-embed/data-model.md.

Revision ID: 0019_kb_chunks
Revises: 0018_raw_store_visibility
Create Date: 2026-11-01
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0019_kb_chunks"
down_revision: Union[str, None] = "0018_raw_store_visibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_TENANT = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
MIN_VECTOR_VERSION = (0, 8)
_KB_TSV = (
    "to_tsvector(CASE WHEN kind = 'wcl' THEN 'simple'::regconfig "
    "ELSE 'english'::regconfig END, text)"
)
_CHAT_TSV = "to_tsvector('english'::regconfig, text)"


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split(".")[:2])


def _content_columns(tsv_sql: str) -> list[sa.Column]:
    """The columns both chunk tables share (text, hash, vector state, keyword index, extra)."""
    return [
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embed_model", sa.String(80), nullable=True),
        sa.Column("embedded_at", _TS, nullable=True),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(tsv_sql, persisted=True)),
        sa.Column("extra", postgresql.JSONB(), nullable=True),
    ]


def _search_indexes(table: str) -> None:
    op.create_index(
        f"ix_{table}_embedding",
        table,
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(f"ix_{table}_tsv", table, ["tsv"], postgresql_using="gin")
    op.create_index(f"ix_{table}_extra", table, ["extra"], postgresql_using="gin")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # vector/tsvector are Postgres-only; SQLite tests build from the models
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    installed = bind.execute(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if installed is None or _version(installed) < MIN_VECTOR_VERSION:
        raise RuntimeError(
            f"pgvector {installed} is installed; the knowledge base needs 0.8 or newer "
            "(ALTER EXTENSION vector UPDATE, or the pgvector/pgvector:pg17-trixie image)"
        )

    op.create_unique_constraint("uq_conversations_id_tenant", "conversations", ["id", "tenant_id"])

    op.create_table(
        "kb_chunks",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column(
            "raw_fetch_id",
            sa.String(64),
            sa.ForeignKey("raw_fetches.query_key", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "guide_id", _UUID, sa.ForeignKey("spec_guides.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("chunk_key", sa.String(200), nullable=False),
        *_content_columns(_KB_TSV),
        sa.Column("report_code", sa.String(32), nullable=True),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("encounter_id", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("fight_id", sa.Integer(), nullable=True),
        sa.Column("kill", sa.Boolean(), nullable=True),
        sa.Column("start_time", _TS, nullable=True),
        sa.Column("players", postgresql.JSONB(), nullable=True),
        sa.Column("region", sa.String(16), nullable=True),
        sa.Column("realm", sa.String(80), nullable=True),
        sa.Column("guild", sa.String(120), nullable=True),
        sa.Column("class_name", sa.String(40), nullable=True),
        sa.Column("spec", sa.String(40), nullable=True),
        sa.Column("role", sa.String(10), nullable=True),
        sa.Column("content_type", sa.String(8), nullable=True),
        sa.Column("patch", sa.String(20), nullable=True),
        sa.Column("section", sa.String(200), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(kind = 'wcl' AND raw_fetch_id IS NOT NULL AND guide_id IS NULL)"
            " OR (kind = 'guide' AND guide_id IS NOT NULL AND raw_fetch_id IS NULL)",
            name="ck_kb_chunks_source",
        ),
        sa.UniqueConstraint("raw_fetch_id", "chunk_key", name="uq_kb_chunks_fetch_key"),
        sa.UniqueConstraint("guide_id", "chunk_key", name="uq_kb_chunks_guide_key"),
    )
    _search_indexes("kb_chunks")
    op.create_index(
        "ix_kb_chunks_players",
        "kb_chunks",
        ["players"],
        postgresql_using="gin",
        postgresql_ops={"players": "jsonb_path_ops"},
    )
    op.create_index("ix_kb_chunks_report_code", "kb_chunks", ["report_code"])
    op.create_index("ix_kb_chunks_encounter", "kb_chunks", ["encounter_id"])
    op.create_index("ix_kb_chunks_class_spec", "kb_chunks", ["class_name", "spec"])
    op.create_index("ix_kb_chunks_kind", "kb_chunks", ["kind"])

    op.create_table(
        "kb_chat_chunks",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "tenant_id", _UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("conversation_id", _UUID, nullable=False),
        sa.Column("message_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("characters", postgresql.JSONB(), nullable=True),
        *_content_columns(_CHAT_TSV),
        sa.ForeignKeyConstraint(
            ["conversation_id", "tenant_id"],
            ["conversations.id", "conversations.tenant_id"],
            ondelete="CASCADE",
            name="fk_kb_chat_chunks_conversation",
        ),
        # The tenant leads the key: a foreign conversation id must fail on the FK, never here
        # (no cross-tenant existence oracle; P7 SEC-001).
        sa.UniqueConstraint(
            "tenant_id", "conversation_id", "message_seq", name="uq_kb_chat_chunks_message"
        ),
    )
    _search_indexes("kb_chat_chunks")
    op.create_index(
        "ix_kb_chat_chunks_characters",
        "kb_chat_chunks",
        ["characters"],
        postgresql_using="gin",
        postgresql_ops={"characters": "jsonb_path_ops"},
    )
    op.create_index(
        "ix_kb_chat_chunks_tenant_created", "kb_chat_chunks", ["tenant_id", "created_at"]
    )

    role = _runtime_role()
    op.execute("ALTER TABLE kb_chat_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE kb_chat_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON kb_chat_chunks USING ({_TENANT}) WITH CHECK ({_TENANT})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON kb_chunks, kb_chat_chunks TO {role}")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON kb_chat_chunks")
    op.drop_table("kb_chat_chunks")
    op.drop_table("kb_chunks")
    op.drop_constraint("uq_conversations_id_tenant", "conversations", type_="unique")
    # The extension stays: dropping it gains nothing and a re-upgrade creates it if missing.
