"""semantic_cache: saved answers found by question meaning (Phase 7B)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "semantic_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("scope_key", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_semantic_cache")),
    )
    # No vector index: a lookup only scans one scope's few entries (filtered by scope_key).
    op.create_index(
        op.f("ix_semantic_cache_scope_key"), "semantic_cache", ["scope_key"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_semantic_cache_scope_key"), table_name="semantic_cache")
    op.drop_table("semantic_cache")
