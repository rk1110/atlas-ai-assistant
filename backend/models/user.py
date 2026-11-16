"""A person who can log in (Phase 7). Conversations and memories belong to one user."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lower-case
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))
    # Never the password itself: "scrypt$<salt>$<hash>" (core/auth.py). A database leak then
    # reveals hashes that take years to brute-force, not passwords.
    password_hash: Mapped[str] = mapped_column(String(300))
    # Document access tags this user may read (permission-aware retrieval). Copied from
    # config/auth.yaml by scripts.seed_users.
    access_tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=lambda: ["public"])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
