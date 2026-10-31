"""Memory settings loaded from `config/memory.yaml` (principle 8)."""

from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from core.config import REPO_ROOT


class ShortTermConfig(BaseModel):
    keep_last_messages: int = Field(default=10, ge=2)


class LongTermConfig(BaseModel):
    enabled: bool = True
    recall_top_k: int = Field(default=5, ge=1)
    duplicate_similarity: float = Field(default=0.9, gt=0, le=1)


class MemoryConfig(BaseModel):
    short_term: ShortTermConfig = ShortTermConfig()
    long_term: LongTermConfig = LongTermConfig()


@lru_cache
def get_memory_config() -> MemoryConfig:
    path = REPO_ROOT / "config" / "memory.yaml"
    if not path.exists():
        return MemoryConfig()
    return MemoryConfig.model_validate(yaml.safe_load(path.read_text()))
