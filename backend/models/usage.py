"""One row per model call (Phase 7B): the ledger behind the cost dashboard and the budget cap.

`messages` only records the final answer's cost. A chat turn also calls the cheap model to
route, rewrite and remember, and the agent team makes up to 14 calls; evals and ingestion
call models with no message at all. Recording every call here, in the gateway, is the only
way the dashboard can answer "where does the money actually go?".
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    # The budget check sums today's rows before every call: the time index keeps that fast.
    __table_args__ = (Index("ix_llm_usage_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    model_id: Mapped[str] = mapped_column(String(100))  # catalog id, e.g. "claude-haiku"
    # The gateway call's name: "chat", "classify_intent", "rewrite_query", "agent", ...
    purpose: Mapped[str] = mapped_column(String(100))
    # Who caused it: "app" (a logged-in user's request), "eval", "ingestion", "script".
    source: Mapped[str] = mapped_column(String(50))
    # SET NULL, not CASCADE: deleting a user must not make past spend disappear.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))  # None = model has no price
