"""RAG settings loaded from `config/rag.yaml` (principle 8: chunk sizes and model names live in
config, not code). Validated on load, so a typo or an impossible combination fails at startup.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from core.config import REPO_ROOT, get_settings


class EmbeddingConfig(BaseModel):
    model: str
    dimensions: int = Field(gt=0)
    batch_size: int = Field(default=32, gt=0)
    query_prefix: str = ""


class ChunkingConfig(BaseModel):
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)
    min_chunk_size: int = Field(default=40, ge=0)

    @model_validator(mode="after")
    def overlap_smaller_than_chunk(self) -> "ChunkingConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class RetrievalConfig(BaseModel):
    top_k: int = Field(default=5, gt=0)


class SourceConfig(BaseModel):
    name: str
    kind: Literal["gitlab_handbook", "acme_docs", "uploads"]
    path: Path  # relative to the repo root

    @property
    def directory(self) -> Path:
        return self.path if self.path.is_absolute() else REPO_ROOT / self.path


class UploadsConfig(BaseModel):
    max_file_mb: float = Field(default=10, gt=0)
    extensions: list[str] = Field(default_factory=lambda: [".md", ".txt", ".html", ".pdf"])


class RagConfig(BaseModel):
    embedding: EmbeddingConfig
    chunking: ChunkingConfig
    retrieval: RetrievalConfig = RetrievalConfig()
    sources: list[SourceConfig] = Field(default_factory=list)
    uploads: UploadsConfig = UploadsConfig()

    def source_of_kind(self, kind: str) -> SourceConfig | None:
        return next((s for s in self.sources if s.kind == kind), None)

    @classmethod
    def from_file(cls, path: Path) -> "RagConfig":
        return cls.model_validate(yaml.safe_load(path.read_text()))


@lru_cache
def get_rag_config() -> RagConfig:
    return RagConfig.from_file(get_settings().rag_file)
