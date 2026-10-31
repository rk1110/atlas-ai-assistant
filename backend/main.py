"""FastAPI application entry point: creates the app and mounts the routers.

Routers live in `api/`; this file only wires them together, so adding a feature means adding
a router file and one `include_router` line, never editing existing routes.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from agents.checkpoints import postgres_checkpointer
from api import (
    analytics,
    chat,
    classify,
    conversations,
    graph,
    knowledge,
    memory,
    models,
    outbox,
)
from api.deps import SessionDep, get_settings
from core.embeddings import get_embedder
from core.tracing import get_tracer

# Show our own INFO logs (uvicorn only configures its own loggers).
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook.

    Startup: load the embedding model in the background (a few seconds), so the first chat
    question doesn't pay for it. In the background, not awaited, so the API is up at once.
    Opens the agent's Postgres checkpointer (Phase 4) for the app's lifetime.
    Shutdown: flush buffered traces so the last requests still show up in Langfuse.
    """
    warm_up = asyncio.create_task(_warm_up_embedder())
    async with postgres_checkpointer():
        yield
    warm_up.cancel()
    get_tracer().flush()


async def _warm_up_embedder() -> None:
    try:
        await get_embedder().embed_query("warm up")
        logger.info("embedding model ready")
    except Exception:  # chat retries the load on first use; don't crash startup
        logger.warning("embedding model warm-up failed", exc_info=True)


app = FastAPI(title="Atlas API", version="0.1.0", lifespan=lifespan)

# CORS: browsers block a page on one origin (localhost:3000) from reading responses from
# another (localhost:8000) unless the server explicitly allows it. We allow only our frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(analytics.router)
app.include_router(chat.router)
app.include_router(classify.router)
app.include_router(conversations.router)
app.include_router(graph.router)
app.include_router(knowledge.router)
app.include_router(memory.router)
app.include_router(models.router)
app.include_router(outbox.router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health")
async def health() -> HealthResponse:
    """Liveness probe. Deliberately does no I/O: a slow database must not make
    Docker think the API process itself is dead (a readiness check comes later)."""
    return HealthResponse(status="ok")


@app.get("/health/ready")
async def ready(session: SessionDep) -> HealthResponse:
    """Readiness probe: can we actually serve requests? Unlike /health, this touches Postgres,
    so a load balancer can stop sending traffic here while the database is unreachable."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return HealthResponse(status="ready")
