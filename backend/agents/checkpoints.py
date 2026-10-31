"""The agent's checkpointer: where a paused run (waiting for approval) is saved.

LangGraph saves the whole graph state after every node. When the approval node pauses,
the saved state is what a later "approve" request resumes from, even after a backend
restart (uvicorn --reload restarts on every save in development). We use LangGraph's own
Postgres saver (principle 5: one database), in its own `langgraph` schema (migration 0007).

Opened once at app startup (main.py lifespan) with a small psycopg connection pool:
LangGraph's saver speaks psycopg, not the asyncpg driver the rest of the app uses.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from core.config import get_settings

logger = logging.getLogger(__name__)

_checkpointer: BaseCheckpointSaver | None = None


@asynccontextmanager
async def postgres_checkpointer() -> AsyncIterator[BaseCheckpointSaver]:
    global _checkpointer
    conninfo = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    async with AsyncConnectionPool(
        conninfo,
        max_size=5,
        open=False,
        kwargs={
            "autocommit": True,  # the saver manages its own transactions
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": "-c search_path=langgraph",
        },
    ) as pool:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()  # creates/migrates its tables in the langgraph schema
        _checkpointer = saver
        try:
            yield saver
        finally:
            _checkpointer = None


def get_checkpointer() -> BaseCheckpointSaver:
    """The app's checkpointer. Outside the running app (scripts, tests) an in-memory one is
    used: runs then can pause and resume within one process, but not survive a restart."""
    global _checkpointer
    if _checkpointer is None:
        logger.info("agent checkpointer: in-memory (Postgres saver not opened)")
        _checkpointer = InMemorySaver()
    return _checkpointer
