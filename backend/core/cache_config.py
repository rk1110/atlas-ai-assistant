"""Semantic cache settings loaded from `config/cache.yaml` (principle 8)."""

from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from core.config import REPO_ROOT


class CacheConfig(BaseModel):
    enabled: bool = True
    similarity_threshold: float = Field(default=0.9, gt=0, le=1)
    ttl_hours: float = Field(default=24, gt=0)


@lru_cache
def get_cache_config() -> CacheConfig:
    path = REPO_ROOT / "config" / "cache.yaml"
    if not path.exists():
        return CacheConfig()
    return CacheConfig.model_validate(yaml.safe_load(path.read_text()))
