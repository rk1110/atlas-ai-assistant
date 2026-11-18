"""Semantic cache entries (Phase 7B): a saved answer, findable by the meaning of its question.

`scope_key` decides who may reuse an entry. It is a hash of everything besides the question
that shaped the answer: the reader's document access, the model, the prompt version, the
facts recalled about the user, and the state of the knowledge base. Two questions only share
an answer when all of those match, so an HR-only answer can never reach someone without HR
access, and an answer mentioning Sam's laptop can never reach Grace.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from models.document import EMBEDDING_DIMENSIONS


class SemanticCacheEntry(Base):
    __tablename__ = "semantic_cache"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scope_key: Mapped[str] = mapped_column(String(64), index=True)  # sha256 hex, see above
    question: Mapped[str] = mapped_column(Text)  # the rewritten (standalone) question
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    model_id: Mapped[str] = mapped_column(String(100))
    # What the answer call cost: every hit saves about this much (the dashboard's "saved").
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    hits: Mapped[int] = mapped_column(default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
