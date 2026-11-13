"""Multimodal settings loaded from `config/multimodal.yaml` (principle 8)."""

from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from core.config import REPO_ROOT


class ImagesConfig(BaseModel):
    max_per_message: int = Field(default=3, ge=1, le=10)
    max_mb: float = Field(default=5, gt=0, le=20)


class IngestionVisionConfig(BaseModel):
    render_dpi: int = Field(default=150, ge=72, le=300)
    max_ocr_pages: int = Field(default=20, ge=1, le=500)


class VoiceConfig(BaseModel):
    model: str = "base"
    compute_type: Literal["int8", "int8_float32", "float32"] = "int8"
    language: str | None = None
    beam_size: int = Field(default=5, ge=1, le=10)
    prompt: str | None = None
    max_seconds: float = Field(default=60, gt=0, le=600)
    max_mb: float = Field(default=10, gt=0, le=50)


class MultimodalConfig(BaseModel):
    images: ImagesConfig = ImagesConfig()
    ingestion: IngestionVisionConfig = IngestionVisionConfig()
    voice: VoiceConfig = VoiceConfig()


@lru_cache
def get_multimodal_config() -> MultimodalConfig:
    path = REPO_ROOT / "config" / "multimodal.yaml"
    if not path.exists():
        return MultimodalConfig()
    return MultimodalConfig.model_validate(yaml.safe_load(path.read_text()))
