"""Guardrail settings loaded from `config/guardrails.yaml` (principle 8)."""

from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from core.config import REPO_ROOT


class InjectionConfig(BaseModel):
    enabled: bool = True
    llm_scan: bool = True
    batch_size: int = Field(default=8, ge=1, le=32)
    model: str | None = None


class PiiConfig(BaseModel):
    enabled: bool = True
    entities: list[str] = Field(default_factory=lambda: ["EMAIL_ADDRESS", "PHONE_NUMBER"])
    allow_email_domains: list[str] = Field(default_factory=list)
    min_score: float = Field(default=0.5, ge=0, le=1)


class OutputConfig(BaseModel):
    enabled: bool = True


class GuardrailsConfig(BaseModel):
    injection: InjectionConfig = InjectionConfig()
    pii: PiiConfig = PiiConfig()
    output: OutputConfig = OutputConfig()


@lru_cache
def get_guardrails_config() -> GuardrailsConfig:
    path = REPO_ROOT / "config" / "guardrails.yaml"
    if not path.exists():
        return GuardrailsConfig()
    return GuardrailsConfig.model_validate(yaml.safe_load(path.read_text()))
