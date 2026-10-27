"""FastAPI application entry point: creates the app and mounts the routers.

Routers live in `api/`; this file only wires them together, so adding a feature means adding
a router file and one `include_router` line, never editing existing routes.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from api import models

app = FastAPI(title="Atlas API", version="0.1.0")
app.include_router(models.router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health")
async def health() -> HealthResponse:
    """Liveness probe. Deliberately does no I/O: a slow database must not make
    Docker think the API process itself is dead (a readiness check comes later)."""
    return HealthResponse(status="ok")
