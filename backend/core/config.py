"""Typed application settings, read from environment variables (and `.env` when run locally).

Why Pydantic Settings instead of `os.environ[...]` scattered around the code:
- Every setting is declared once, with a type. A missing required value or a wrong type fails
  at startup with a clear error, instead of crashing mid-request later.
- Secrets are `SecretStr`, so they print as '**********' in logs, tracebacks and reprs.
- Inside Docker the values come from the container's environment (docker-compose.yml);
  when you run code on your Mac they are read from the repo-root `.env` file.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/core/config.py -> parents[2] is the repo root (/app inside the container).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        # .env also holds Langfuse/MinIO server secrets the backend doesn't use; ignore them.
        extra="ignore",
    )

    # --- LLM providers (optional: a missing key just marks those models unavailable) ---
    anthropic_api_key: SecretStr | None = None
    ollama_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- Data stores ---
    database_url: str
    redis_url: str | None = None

    # --- Observability (Langfuse). Keys missing = tracing off, app still works ---
    langfuse_host: str = "http://localhost:3001"  # where the SDK sends traces
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_environment: str = "local"  # filter traces by environment in the Langfuse UI
    langfuse_ui_url: str = "http://localhost:3001"  # what your browser opens (trace links)
    langfuse_project_id: str = "atlas"  # matches LANGFUSE_INIT_PROJECT_ID in docker-compose.yml

    # --- App behaviour ---
    assistant_name: str = "Atlas"  # fills $assistant_name in prompts; rename the product here
    chat_history_limit: int = 20  # messages re-sent to the model each turn (short-term memory)

    # --- Versioned config that lives in the repo, not in .env ---
    models_file: Path = REPO_ROOT / "config" / "models.yaml"
    prompts_dir: Path = REPO_ROOT / "prompts"

    @field_validator(
        "anthropic_api_key",
        "ollama_api_key",
        "langfuse_public_key",
        "langfuse_secret_key",
        mode="before",
    )
    @classmethod
    def empty_means_missing(cls, value: object) -> object:
        """docker-compose passes unset optional keys as "" (`${VAR:-}`); treat that as None."""
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    """One shared Settings instance. Cached so `.env` is parsed once, and usable as a
    FastAPI dependency (tests override it with `app.dependency_overrides`)."""
    return Settings()
