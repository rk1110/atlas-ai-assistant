"""Agent settings loaded from `config/agent.yaml` (principle 8: flags live in config)."""

from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from core.config import REPO_ROOT


class AgentConfig(BaseModel):
    enabled: bool = True
    route_intents: list[str] = Field(default_factory=lambda: ["action_request"])
    mode: Literal["single", "team"] = "team"
    max_model_calls: int = Field(default=6, ge=1, le=20)
    team_max_model_calls: int = Field(default=14, ge=4, le=40)


@lru_cache
def get_agent_config() -> AgentConfig:
    path = REPO_ROOT / "config" / "agent.yaml"
    if not path.exists():
        return AgentConfig()
    return AgentConfig.model_validate(yaml.safe_load(path.read_text()))
