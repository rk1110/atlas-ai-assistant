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


class Pricing(BaseModel):
    """USD per million tokens. Ours, from the provider's price page, because LiteLLM's bundled
    map lags new models (it returned $0 for Haiku 5.5): a wrong price hides real spend."""

    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok) / 1e6


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
    # Can it read images (Phase 6)? A text-only model sent an image errors or ignores it, so
    # the chat routes image questions to `defaults.vision` instead.
    vision: bool = False
    pricing: Pricing | None = None  # None = use LiteLLM's price map (may not know the model)

    @model_validator(mode="after")
    def one_api_base_source(self) -> "ModelEntry":
        if self.api_base and self.api_base_setting:
            raise ValueError(f"{self.id}: set api_base or api_base_setting, not both")
        return self


class CatalogDefaults(BaseModel):
    chat: str
    cheap: str
    vision: str | None = None  # answers (and describes) messages with images; None = no vision


class BudgetConfig(BaseModel):
    """Phase 7B spending cap: today's total across every model call, all users."""

    daily_usd: float | None = Field(default=None, gt=0)  # None = no cap


AUTO_MODEL_ID = "auto"  # the model switcher's "Auto" choice; resolved per message (Phase 7B)


class RoutingConfig(BaseModel):
    """Phase 7B model routing: in "Auto", the intent classifier's complexity label picks the
    model, so easy questions don't pay for the strongest one."""

    enabled: bool = False
    label: str = "Auto"
    simple: str | None = None  # model for one-fact lookups (the cheap one)
    complex: str | None = None  # model for everything else, and for every agent turn


class ModelAvailability(BaseModel):
    available: bool
    reason: str | None = None  # human-readable hint when unavailable


class ModelCatalog:
    def __init__(
        self,
        entries: list[ModelEntry],
        defaults: CatalogDefaults,
        settings: Settings,
        budget: BudgetConfig | None = None,
        routing: RoutingConfig | None = None,
    ):
        self._entries = {entry.id: entry for entry in entries}
        self.defaults = defaults
        self.budget = budget or BudgetConfig()
        self.routing = routing or RoutingConfig()
        self._settings = settings
        self._validate_references()

    @classmethod
    def from_yaml(cls, path: Path, settings: Settings) -> "ModelCatalog":
        raw = yaml.safe_load(path.read_text())
        entries = [ModelEntry.model_validate(item) for item in raw["models"]]
        defaults = CatalogDefaults.model_validate(raw["defaults"])
        budget = BudgetConfig.model_validate(raw.get("budget") or {})
        routing = RoutingConfig.model_validate(raw.get("routing") or {})
        return cls(entries, defaults, settings, budget, routing)

    def _validate_references(self) -> None:
        """Fail fast on config mistakes: duplicate ids, bad defaults, unknown setting names."""
        for default in (self.defaults.chat, self.defaults.cheap):
            if default not in self._entries:
                raise ValueError(f"models.yaml default '{default}' is not a model id")
        if self.routing.enabled:
            for model in (self.routing.simple, self.routing.complex):
                if model not in self._entries:
                    raise ValueError(f"models.yaml routing model '{model}' is not a model id")
        vision = self.defaults.vision
        if vision is not None and not getattr(self._entries.get(vision), "vision", False):
            raise ValueError(f"models.yaml vision default '{vision}' is not a vision model")
        for entry in self._entries.values():
            for setting in (entry.api_key_setting, entry.api_base_setting):
                if setting and setting not in Settings.model_fields:
                    raise ValueError(f"{entry.id}: unknown setting '{setting}'")

    def list(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def get(self, model_id: str) -> ModelEntry | None:
        return self._entries.get(model_id)

    @property
    def auto_enabled(self) -> bool:
        return self.routing.enabled

    def is_selectable(self, model_id: str) -> bool:
        """What a request may ask for: a real model, or "auto" when routing is on."""
        return model_id in self._entries or (model_id == AUTO_MODEL_ID and self.auto_enabled)

    @property
    def default_selection(self) -> str:
        """Preselected in the UI: "Auto" when routing is on. `defaults.chat` stays a real model
        (scripts, the MCP server and the graph build need one)."""
        return AUTO_MODEL_ID if self.auto_enabled else self.defaults.chat

    def routed(self, complex_: bool) -> str:
        """The model "Auto" resolves to. Only call with routing on."""
        model = self.routing.complex if complex_ else self.routing.simple
        assert model is not None
        return model

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
