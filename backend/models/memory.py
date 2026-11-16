"""Long-term memory (Phase 4): lasting facts about the user, with embeddings for recall.

Each user has their own facts (Phase 7 added user_id). Each fact is a short
sentence ("Works in the Pune office.") plus its embedding, so the facts relevant to a new
question can be found the same way passages are: nearest vectors.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from models.document import EMBEDDING_DIMENSIONS


class MemoryRecord(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Phase 7: whose fact it is. Recall, listing and forgetting only ever see the user's own.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    source_conversation_id: Mapped[uuid.UUID | None]  # where the user said it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
