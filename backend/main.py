"""FastAPI application entry point: creates the app and mounts the routers.

Routers live in `api/`; this file only wires them together, so adding a feature means adding
a router file and one `include_router` line, never editing existing routes.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from api import chat, classify, conversations, models
from api.deps import SessionDep, get_settings
from core.tracing import get_tracer

# Show our own INFO logs (uvicorn only configures its own loggers).
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook. On shutdown, flush buffered traces so the last requests
    before a restart still show up in Langfuse."""
    yield
    get_tracer().flush()


app = FastAPI(title="Atlas API", version="0.1.0", lifespan=lifespan)

# CORS: browsers block a page on one origin (localhost:3000) from reading responses from
# another (localhost:8000) unless the server explicitly allows it. We allow only our frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(chat.router)
app.include_router(classify.router)
app.include_router(conversations.router)
app.include_router(models.router)


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
