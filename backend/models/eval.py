"""Eval runs and their per-question results (principle 5: eval results live in Postgres).

One EvalRun = one execution of the golden set against one model + prompt version.
Comparing runs is how a change becomes a number: "prompt v2 cut latency by 30% with the
same answers". Phase 2 adds retrieval metrics and Phase 3 adds quality scores as new nullable
columns, so old runs stay comparable.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_id: Mapped[str] = mapped_column(String(100))
    prompt_ref: Mapped[str | None] = mapped_column(String(100))  # e.g. "chat_system@v1"
    golden_set_version: Mapped[int]
    notes: Mapped[str | None] = mapped_column(Text)  # what changed, e.g. "try prompt v2"
    # Summary, so comparing runs doesn't require re-aggregating every result row.
    question_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    avg_latency_ms: Mapped[int | None]
    total_input_tokens: Mapped[int] = mapped_column(default=0)
    total_output_tokens: Mapped[int] = mapped_column(default=0)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))

    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(100))  # stable id from golden_set.yaml
    question: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str] = mapped_column(Text)
    expected_sources: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    answer: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(32))
    latency_ms: Mapped[int | None]
    time_to_first_token_ms: Mapped[int | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    trace_id: Mapped[str | None] = mapped_column(String(64))

    run: Mapped[EvalRun] = relationship(back_populates="results")
