"""GET /api/models: the model list for the frontend's model switcher.

The frontend never hard-codes model names; it renders whatever this returns, greying out
models that can't be used right now (missing key, local server not running).
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import CatalogDep

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
    return ModelsResponse(
        models=[
            ModelInfo(
                id=entry.id,
                label=entry.label,
                provider=entry.provider,
                available=status.available,
                unavailable_reason=status.reason,
            )
            for entry, status in zip(entries, availabilities, strict=True)
        ],
        default_model=catalog.defaults.chat,
    )
