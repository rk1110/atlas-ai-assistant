"""Documents in the knowledge base, and the chunks they're split into.

    documents  one row per source document (a handbook page, a policy, an uploaded PDF)
    chunks     one row per passage: its text, where it sits in the document, and its
               embedding vector, which is what retrieval searches

Chunks live in Postgres next to everything else (principle 5) thanks to pgvector: the
`embedding` column is a real vector type with its own index, so "find the 5 nearest vectors"
is a normal SQL query that can be combined with WHERE filters and joins.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

# Must match config/rag.yaml (embedding.dimensions); the embedder checks this at load time.
EMBEDDING_DIMENSIONS = 384

DOCUMENT_STATUSES = ("pending", "processing", "ready", "failed")


class DocumentRecord(Base):
    """Named *Record* to avoid clashing with core.interfaces.Document, the raw fetched
    document that DataSources produce. This is what we store after processing it."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')", name="status_valid"
        ),
        Index("ix_documents_source", "source"),
    )

    id: Mapped[str] = mapped_column(String(500), primary_key=True)  # e.g. "acme-docs:hr/x.md"
    source: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(20))
    # sha256 of the raw content: re-ingestion skips documents whose hash hasn't changed.
    content_hash: Mapped[str] = mapped_column(String(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    access_tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=lambda: ["public"])
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str | None] = mapped_column(Text)  # why ingestion failed, shown in the UI
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["ChunkRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class ChunkRecord(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_document_ordinal", "document_id", "ordinal", unique=True),
        # HNSW: an approximate-nearest-neighbour index. Without it, every search compares the
        # query with every chunk (fine for 2,000 chunks, slow for 2 million). HNSW builds a
        # layered graph of neighbours and walks it, checking a tiny fraction of rows, at the
        # cost of occasionally missing the true nearest one. `vector_cosine_ops` = the index
        # is built for cosine distance, the `<=>` operator we search with.
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int]  # position in the document: 0, 1, 2...
    text: Mapped[str] = mapped_column(Text)  # what the model reads and the citation shows
    heading: Mapped[str | None] = mapped_column(Text)  # e.g. "Values > Iteration"
    token_count: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[DocumentRecord] = relationship(back_populates="chunks")
