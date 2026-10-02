"""SQLAlchemy ORM models for app state (conversations + messages)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# JSONB on PostgreSQL, plain JSON on SQLite (so the same model backs tests too).
_JSON = JSON().with_variant(JSONB(), "postgresql")

# Generic UUID type: renders as native ``uuid`` on PostgreSQL and ``CHAR(32)`` on
# SQLite, so the same models back both production (Postgres) and fast unit tests.
_UUID = Uuid(as_uuid=True)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.seq",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "seq", name="uq_message_conv_seq"),)

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(10))  # "user" | "agent"
    content: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    # "complete" | "partial" — set to "partial" when a streamed agent reply is
    # interrupted (US2 / FR-009), so the UI/PDF can flag unfinished answers.
    status: Mapped[str] = mapped_column(String(10), server_default="complete", default="complete")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class TrackedRaid(Base):
    """A Warcraft Logs report the user has successfully pulled data for (US1).

    Keyed by ``report_code`` (natural dedup key) and standalone — it outlives any
    single conversation, so a deleted chat only nulls ``last_conversation_id``.
    """

    __tablename__ = "tracked_raids"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    report_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200))
    zone: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guild: Mapped[str | None] = mapped_column(String(120), nullable=True)
    report_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # US2/US4: deduped distinct boss list for this report (list of
    # {encounter_id, name, difficulty, kill}); merged on each get_report_fights.
    encounters: Mapped[list | None] = mapped_column(_JSON, nullable=True)


class CapturedGraph(Base):
    """Graph JSON the agent fetched during a conversation, kept for PDF rendering (US5)."""

    __tablename__ = "captured_graphs"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_code: Mapped[str] = mapped_column(String(32))
    data_type: Mapped[str] = mapped_column(String(40))
    fight_id: Mapped[int] = mapped_column(Integer, default=0)
    source_id: Mapped[int] = mapped_column(Integer, default=0)
    graph_json: Mapped[dict] = mapped_column(_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
