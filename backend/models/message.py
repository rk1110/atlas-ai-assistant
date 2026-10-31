"""One message in a conversation: what the user asked or what the assistant answered.

Assistant messages also store *how* they were produced (model, prompt version, tokens, cost,
latency, trace id). That makes every answer explainable later, and it is the raw data for
the Analytics page (Phase 3/7) without needing to query Langfuse.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

if TYPE_CHECKING:
    from models.conversation import Conversation


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Enforced by Postgres itself, so even a bug elsewhere can't store a bad role.
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="role_valid"),
        # The hot query: "all messages of conversation X in order". One index serves it.
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ---- Provenance: filled for assistant messages only ----
    model_id: Mapped[str | None] = mapped_column(String(100))  # catalog id, e.g. "gpt-oss-cloud"
    prompt_ref: Mapped[str | None] = mapped_column(String(100))  # e.g. "chat_system@v1"
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    # Numeric, not float: money must not suffer binary rounding when summed in dashboards.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latency_ms: Mapped[int | None]
    time_to_first_token_ms: Mapped[int | None]
    trace_id: Mapped[str | None] = mapped_column(String(64))  # Langfuse trace (step 5)
    # Set when generation failed part-way: the partial answer is kept, with the reason.
    error_code: Mapped[str | None] = mapped_column(String(32))
    # The sources the answer cited, as CitationEvent dicts (Phase 2). JSONB rather than a
    # table: they're always read together with their message and never queried on their own.
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Agent answers (Phase 4): steps, tool calls and approval cards, as a core.events.AgentLog.
    agent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
