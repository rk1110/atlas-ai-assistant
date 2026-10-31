"""keyword search: chunks.search_vector (tsvector) + GIN index

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30

Existing chunks are backfilled from their document's title + heading + text, the same
expression ingestion uses (models.document.search_vector), so no re-ingest is needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    op.execute(
        """
        UPDATE chunks AS c
        SET search_vector = to_tsvector(
            'english', d.title || E'\\n' || coalesce(c.heading, '') || E'\\n' || c.text
        )
        FROM documents AS d
        WHERE d.id = c.document_id
        """
    )
    op.create_index(
        "ix_chunks_search_vector_gin", "chunks", ["search_vector"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_search_vector_gin", table_name="chunks", postgresql_using="gin")
    op.drop_column("chunks", "search_vector")
