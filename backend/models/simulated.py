"""Simulated Jira and Slack (Phase 4): where the agent's write tools "send" things.

Atlas never touches real company systems in development. These two tables stand in for Jira
and Slack, so the whole flow (agent proposes, human approves, tool writes, user sees the
result) is real except the final destination. Phase 5 puts the same data behind MCP servers,
which is how a real Jira or Slack would be plugged in.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class SimTicket(Base):
    __tablename__ = "sim_tickets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(20), unique=True)  # e.g. "IT-1001"
    project: Mapped[str] = mapped_column(String(10))
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="Open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimSlackMessage(Base):
    __tablename__ = "sim_slack_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
