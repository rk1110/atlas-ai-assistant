"""judge metrics + run config on evals, search_query on results

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30

All nullable: Phase 1-2 runs keep their rows and simply have no judge scores.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCORES = ("faithfulness", "answer_correctness", "context_precision")


def upgrade() -> None:
    op.add_column("eval_runs", sa.Column("judge_model", sa.String(length=100), nullable=True))
    op.add_column("eval_runs", sa.Column("config", postgresql.JSONB(), nullable=True))
    op.add_column("eval_results", sa.Column("search_query", sa.Text(), nullable=True))
    op.add_column("eval_results", sa.Column("judgement", postgresql.JSONB(), nullable=True))
    for table in ("eval_runs", "eval_results"):
        for column in SCORES:
            op.add_column(table, sa.Column(column, sa.Float(), nullable=True))


def downgrade() -> None:
    for table in ("eval_runs", "eval_results"):
        for column in SCORES:
            op.drop_column(table, column)
    op.drop_column("eval_results", "judgement")
    op.drop_column("eval_results", "search_query")
    op.drop_column("eval_runs", "config")
    op.drop_column("eval_runs", "judge_model")
