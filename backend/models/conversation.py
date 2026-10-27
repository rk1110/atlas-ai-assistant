"""A chat conversation: the container for messages. Listed in the frontend sidebar."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

if TYPE_CHECKING:  # avoids a circular import at runtime; only type checkers need it
    from models.message import Message


class Conversation(Base):
    __tablename__ = "conversations"

    # The frontend generates this UUID before the first message (decision log, Phase 1 plan),
    # so no "conversation created" event is needed. UUIDs can't be guessed or enumerated.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # Short label for the sidebar; set from the first user message (step 4).
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Bumped whenever a message is added, so the sidebar can sort by recent activity.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        order_by="Message.created_at",
        cascade="all, delete-orphan",  # deleting a conversation deletes its messages
        passive_deletes=True,  # ...and lets Postgres do it (ON DELETE CASCADE), in one statement
    )
