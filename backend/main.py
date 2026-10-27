"""FastAPI application entry point: creates the app and mounts the routers.

Routers live in `api/`; this file only wires them together, so adding a feature means adding
a router file and one `include_router` line, never editing existing routes.
"""

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api import chat, conversations, models
from api.deps import SessionDep

# Show our own INFO logs (uvicorn only configures its own loggers).
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Atlas API", version="0.1.0")
app.include_router(chat.router)
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
