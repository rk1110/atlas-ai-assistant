"""Database setup: async SQLAlchemy engine, session factory and the ORM base class.

Why async: a chat request spends most of its time waiting (on the LLM, on Postgres). With an
async driver (asyncpg), one server process can serve many requests while each one waits,
instead of tying up a thread per request.

Key objects:
- engine:  owns the connection *pool* (connections are reused, because opening one is slow)
- session: one unit of work; you add/query objects, then commit (or roll back) together
- Base:    parent class of every table model in `models/`
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings

# Deterministic constraint names (e.g. "fk_messages_conversation_id_conversations"), so Alembic
# can find and drop them later. Without this, Postgres invents names and downgrades break.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache
def get_engine() -> AsyncEngine:
    """Created lazily on first use (not at import), so importing models never needs a DB."""
    return create_async_engine(
        get_settings().database_url,
        # Check a pooled connection is alive before using it (e.g. after Postgres restarted).
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: objects stay readable after commit. Async code can't lazily
    # reload expired attributes, so the default (True) causes confusing errors after commit.
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    async with get_session_factory()() as session:
        yield session
