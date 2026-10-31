"""Long-term memory (Phase 4): lasting facts about the user, with embeddings for recall.

One user for now (login arrives in Phase 7, which adds a user_id here). Each fact is a short
sentence ("Works in the Pune office.") plus its embedding, so the facts relevant to a new
question can be found the same way passages are: nearest vectors.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from models.document import EMBEDDING_DIMENSIONS


class MemoryRecord(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    source_conversation_id: Mapped[uuid.UUID | None]  # where the user said it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
