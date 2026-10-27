"""FastAPI dependency providers: the objects routes receive via `Depends(...)`.

Why dependency injection instead of importing globals: tests can swap any of these with
`app.dependency_overrides[get_gateway] = lambda: FakeGateway()`, so route tests never call a
real LLM (fast, free, deterministic). That's exactly how the step 9 chat tests will work.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from core.config import Settings, get_settings
from core.llm import LLMGateway
from core.model_catalog import ModelCatalog


@lru_cache
def get_catalog() -> ModelCatalog:
    settings = get_settings()
    return ModelCatalog.from_yaml(settings.models_file, settings)


@lru_cache
def get_gateway() -> LLMGateway:
    return LLMGateway(get_catalog())


SettingsDep = Annotated[Settings, Depends(get_settings)]
CatalogDep = Annotated[ModelCatalog, Depends(get_catalog)]
GatewayDep = Annotated[LLMGateway, Depends(get_gateway)]
