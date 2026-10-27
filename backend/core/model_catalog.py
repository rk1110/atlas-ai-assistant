"""The catalog of selectable models, loaded from `config/models.yaml`.

Why a catalog instead of passing raw model strings around:
- The frontend only ever sends a short `id` ("claude-sonnet"). The backend decides what that
  means (provider, model string, parameters), so users can't request arbitrary models.
- Per-model parameters live in config. Claude 5.5 rejects `temperature` but Ollama models accept
  it; that difference is data in YAML, not `if provider == ...` branches in code.
- It answers "is this model usable right now?" (key present? local server running?) so the UI
  can grey out models instead of letting users hit an error.
"""

import asyncio
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, model_validator

from core.config import Settings


class ModelEntry(BaseModel):
    """One model from models.yaml. Validated on load, so a typo fails at startup."""

    id: str
    label: str
    provider: str
    litellm_model: str
    api_key_setting: str | None = None
    api_base: str | None = None
    api_base_setting: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    # How complete_structured gets JSON: "native" = provider enforces the schema,
    # "prompt" = schema described in the prompt + validation + one retry.
    structured_output: Literal["native", "prompt"] = "native"
    extra_headers: dict[str, str] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def one_api_base_source(self) -> "ModelEntry":
        if self.api_base and self.api_base_setting:
            raise ValueError(f"{self.id}: set api_base or api_base_setting, not both")
        return self


class CatalogDefaults(BaseModel):
    chat: str
    cheap: str


class ModelAvailability(BaseModel):
    available: bool
    reason: str | None = None  # human-readable hint when unavailable


class ModelCatalog:
    def __init__(self, entries: list[ModelEntry], defaults: CatalogDefaults, settings: Settings):
        self._entries = {entry.id: entry for entry in entries}
        self.defaults = defaults
        self._settings = settings
        self._validate_references()

    @classmethod
    def from_yaml(cls, path: Path, settings: Settings) -> "ModelCatalog":
        raw = yaml.safe_load(path.read_text())
        entries = [ModelEntry.model_validate(item) for item in raw["models"]]
        return cls(entries, CatalogDefaults.model_validate(raw["defaults"]), settings)

    def _validate_references(self) -> None:
        """Fail fast on config mistakes: duplicate ids, bad defaults, unknown setting names."""
        for default in (self.defaults.chat, self.defaults.cheap):
            if default not in self._entries:
                raise ValueError(f"models.yaml default '{default}' is not a model id")
        for entry in self._entries.values():
            for setting in (entry.api_key_setting, entry.api_base_setting):
                if setting and setting not in Settings.model_fields:
                    raise ValueError(f"{entry.id}: unknown setting '{setting}'")

    def list(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def get(self, model_id: str) -> ModelEntry | None:
        return self._entries.get(model_id)

    def api_key(self, entry: ModelEntry) -> str | None:
        """The secret for this model's provider, unwrapped only at the moment of the call."""
        if not entry.api_key_setting:
            return None
        secret = getattr(self._settings, entry.api_key_setting)
        return secret.get_secret_value() if secret else None

    def api_base(self, entry: ModelEntry) -> str | None:
        if entry.api_base_setting:
            return getattr(self._settings, entry.api_base_setting)
        return entry.api_base

    async def availability(self, entry: ModelEntry) -> ModelAvailability:
        if entry.api_key_setting and not self.api_key(entry):
            env_var = entry.api_key_setting.upper()
            return ModelAvailability(available=False, reason=f"Set {env_var} in .env")
        if entry.api_base_setting:
            # Local server (no key): only usable if something is listening at that address.
            base = self.api_base(entry) or ""
            if not await _is_listening(base):
                return ModelAvailability(available=False, reason=f"Nothing running at {base}")
        return ModelAvailability(available=True)


async def _is_listening(url: str, timeout_s: float = 0.5) -> bool:
    """Cheap TCP check: can we open a connection to the URL's host:port? (no HTTP request)"""
    parsed = urlparse(url)
    if not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(parsed.hostname, port), timeout=timeout_s
        )
    except (OSError, TimeoutError):
        return False
    writer.close()
    await writer.wait_closed()
    return True
