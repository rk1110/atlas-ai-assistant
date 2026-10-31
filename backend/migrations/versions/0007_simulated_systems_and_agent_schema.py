"""simulated Jira/Slack tables + a `langgraph` schema for agent checkpoints

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31

The agent's checkpoints (paused runs waiting for approval) are stored by LangGraph's own
Postgres saver, which creates and migrates its tables itself. They live in their own schema,
`langgraph`, so Alembic (which only compares the default schema) never tries to drop them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sim_tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=20), nullable=False),
        sa.Column("project", sa.String(length=10), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "sim_slack_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS langgraph CASCADE")
    op.drop_table("sim_slack_messages")
    op.drop_table("sim_tickets")
