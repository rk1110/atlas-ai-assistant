"""GET /api/models: the model list for the frontend's model switcher.

The frontend never hard-codes model names; it renders whatever this returns, greying out
models that can't be used right now (missing key, local server not running).
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import CatalogDep
from core.model_catalog import AUTO_MODEL_ID

router = APIRouter(prefix="/api", tags=["models"])


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str
    available: bool
    unavailable_reason: str | None


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    default_model: str


@router.get("/models")
async def list_models(catalog: CatalogDep) -> ModelsResponse:
    entries = catalog.list()
    # Check all models concurrently: local-server probes can take up to 0.5 s each.
    availabilities = await asyncio.gather(*(catalog.availability(e) for e in entries))
    models = [
        ModelInfo(
            id=entry.id,
            label=entry.label,
            provider=entry.provider,
            available=status.available,
            unavailable_reason=status.reason,
        )
        for entry, status in zip(entries, availabilities, strict=True)
    ]
    if catalog.auto_enabled:  # Phase 7B: first in the list, usable when both its models are
        routed = [m for m in models if m.id in (catalog.routed(False), catalog.routed(True))]
        down = next((m for m in routed if not m.available), None)
        auto = ModelInfo(
            id=AUTO_MODEL_ID,
            label=catalog.routing.label,
            provider="routing",
            available=down is None,
            unavailable_reason=f"{down.label}: {down.unavailable_reason}" if down else None,
        )
        models.insert(0, auto)
    return ModelsResponse(models=models, default_model=catalog.default_selection)
