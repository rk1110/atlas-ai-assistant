"""FastAPI application entry point.

Step 2 only exposes `/health` so Docker can tell the container is alive.
Step 3 adds config, the database and routers.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Atlas API", version="0.1.0")


class HealthResponse(BaseModel):
    status: str


@app.get("/health")
async def health() -> HealthResponse:
    """Liveness probe. Deliberately does no I/O: a slow database must not make
    Docker think the API process itself is dead (a readiness check comes later)."""
    return HealthResponse(status="ok")
