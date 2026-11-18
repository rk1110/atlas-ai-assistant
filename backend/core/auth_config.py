"""Login, permission and rate-limit settings loaded from `config/auth.yaml` (principle 8)."""

import os
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from core.config import REPO_ROOT


class SessionConfig(BaseModel):
    hours: float = Field(default=12, gt=0, le=24 * 30)
    secure_cookie: bool = False


class DemoUser(BaseModel):
    email: str
    name: str
    role: str | None = None
    access: list[str] = Field(default_factory=lambda: ["public"])
    owns_existing_data: bool = False


class RateLimits(BaseModel):
    per_minute: int = Field(default=10, ge=1)
    per_day: int = Field(default=200, ge=1)


class AuthConfig(BaseModel):
    session: SessionConfig = SessionConfig()
    users: list[DemoUser] = Field(default_factory=list)
    rate_limits: RateLimits = RateLimits()


@lru_cache
def get_auth_config() -> AuthConfig:
    path = REPO_ROOT / "config" / "auth.yaml"
    config = (
        AuthConfig.model_validate(yaml.safe_load(path.read_text()))
        if path.exists()
        else AuthConfig()
    )
    # Phase 7D: the deployment decides, not the repo. docker-compose.prod.yml sets
    # AUTH_SECURE_COOKIE=true (HTTPS-only cookies); local dev keeps auth.yaml's false.
    if (flag := os.environ.get("AUTH_SECURE_COOKIE")) is not None:
        config.session.secure_cookie = flag.strip().lower() in ("1", "true", "yes")
    return config
