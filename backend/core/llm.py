"""The LLM gateway: the ONLY place in Atlas that calls a language model (principle 2).

Every model call goes through `LLMGateway`, which wraps LiteLLM. LiteLLM gives one
OpenAI-style interface over many providers (Anthropic, Ollama, OpenAI, ...), so switching
models is a config change in `config/models.yaml`, never a code change.

Owning this single choke point is what makes later phases cheap:
- step 5 adds Langfuse tracing here once, and every call in the app is traced;
- Phase 7 adds caching, routing and cost caps here once.

The gateway streams *provider-neutral* chunks (`TextDelta`, then one `Completion`). It knows
nothing about HTTP or SSE; the chat service (step 4) turns these into `StreamEvent`s.
"""

import os
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

# Use the price/capability map bundled with the pinned LiteLLM version instead of downloading
# the latest one from GitHub at import time: reproducible costs, works offline, no runtime fetch.
# Must be set before `import litellm`.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm
from pydantic import BaseModel, Field

from core.model_catalog import ModelCatalog, ModelEntry

litellm.suppress_debug_info = True  # LiteLLM otherwise prints help banners on every error


class ChatMessage(BaseModel):
    """One message in a conversation, in the role/content shape every chat model accepts."""

    role: Literal["system", "user", "assistant"]
    content: str


class TextDelta(BaseModel):
    """A small piece of generated text ("token" in loose speak; often a few characters)."""

    type: Literal["delta"] = "delta"
    text: str


class Completion(BaseModel):
    """Sent once, after the last delta: what the call cost and how it ended."""

    type: Literal["completion"] = "completion"
    model_id: str
    litellm_model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None  # None when LiteLLM has no price for the model (e.g. Ollama)
    latency_ms: int
    time_to_first_token_ms: int | None
    finish_reason: str | None  # "stop" = natural end, "length" = hit max_tokens


LLMChunk = Annotated[TextDelta | Completion, Field(discriminator="type")]

LLMErrorKind = Literal[
    "unknown_model",
    "unavailable",
    "auth",
    "rate_limit",
    "bad_request",
    "context_too_long",
    "refusal",
    "timeout",
    "billing",
    "provider_error",
]


class LLMError(Exception):
    """A model call failed. `kind` lets callers react (retry? tell the user to add a key?)
    without depending on any provider's or LiteLLM's exception classes.

    `message` is short and safe to show users; `detail` is the provider's raw error
    (redacted), meant for logs and debugging only.
    """

    def __init__(self, kind: LLMErrorKind, message: str, model_id: str, detail: str | None = None):
        super().__init__(f"{message} ({detail})" if detail else message)
        self.kind = kind
        self.message = message
        self.model_id = model_id
        self.detail = detail


class LLMGateway:
    def __init__(self, catalog: ModelCatalog):
        self._catalog = catalog

    async def stream_chat(
        self, model_id: str, messages: list[ChatMessage]
    ) -> AsyncIterator[LLMChunk]:
        """Stream a chat completion: yields `TextDelta`s as they arrive, then one `Completion`.

        Why stream: a full answer takes seconds; streaming shows the first words after
        ~0.5-2 s instead of making the user stare at a spinner (time-to-first-token).
        """
        entry = await self._usable_entry(model_id)
        started = time.perf_counter()
        first_token_at: float | None = None
        finish_reason: str | None = None
        usage: Any = None

        try:
            response = await litellm.acompletion(
                messages=[m.model_dump() for m in messages],
                stream=True,
                # Ask the provider to append a final chunk with token counts (for cost).
                stream_options={"include_usage": True},
                **self._call_kwargs(entry),
            )
            async for chunk in response:
                if chunk.choices:
                    choice = chunk.choices[0]
                    text = choice.delta.content
                    if text:
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        yield TextDelta(text=text)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
        except Exception as exc:
            raise self._translate_error(exc, entry) from exc

        if finish_reason == "content_filter":
            # LiteLLM maps Anthropic's `stop_reason: "refusal"` (safety classifier) to this.
            raise LLMError("refusal", "The model declined to answer this request.", entry.id)

        yield self._completion(entry, usage, finish_reason, started, first_token_at)

    async def _usable_entry(self, model_id: str) -> ModelEntry:
        entry = self._catalog.get(model_id)
        if entry is None:
            raise LLMError("unknown_model", f"Unknown model '{model_id}'", model_id)
        availability = await self._catalog.availability(entry)
        if not availability.available:
            raise LLMError("unavailable", availability.reason or "Model unavailable", model_id)
        return entry

    def _call_kwargs(self, entry: ModelEntry) -> dict[str, Any]:
        """Everything model-specific comes from config: model string, endpoint, key, params."""
        kwargs: dict[str, Any] = {"model": entry.litellm_model, **entry.params}
        if api_key := self._catalog.api_key(entry):
            kwargs["api_key"] = api_key
        if api_base := self._catalog.api_base(entry):
            kwargs["api_base"] = api_base
        if entry.extra_headers:
            kwargs["extra_headers"] = entry.extra_headers
        if entry.extra_body:
            kwargs["extra_body"] = entry.extra_body
        return kwargs

    @staticmethod
    def _completion(
        entry: ModelEntry,
        usage: Any,
        finish_reason: str | None,
        started: float,
        first_token_at: float | None,
    ) -> Completion:
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        try:
            prompt_cost, completion_cost = litellm.cost_per_token(
                model=entry.litellm_model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )
            cost: float | None = prompt_cost + completion_cost
        except Exception:  # noqa: BLE001 - no price known for this model (e.g. Ollama)
            cost = None
        return Completion(
            model_id=entry.id,
            litellm_model=entry.litellm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=round((time.perf_counter() - started) * 1000),
            time_to_first_token_ms=(
                round((first_token_at - started) * 1000) if first_token_at else None
            ),
            finish_reason=finish_reason,
        )

    def _translate_error(self, exc: Exception, entry: ModelEntry) -> LLMError:
        """Map LiteLLM's exceptions to our small set of kinds. Order matters: LiteLLM's
        classes inherit from each other, so the most specific checks come first."""
        detail = self._redact(str(exc))[:300]
        if "credit balance is too low" in detail:
            # Anthropic sends "no credit" as a generic 400; it needs its own message in the UI.
            return LLMError(
                "billing",
                "No API credit for this provider: add credit or pick another model",
                entry.id,
                detail,
            )
        checks: list[tuple[type[Exception], LLMErrorKind, str]] = [
            (
                litellm.ContextWindowExceededError,
                "context_too_long",
                "Conversation too long for this model",
            ),
            (litellm.ContentPolicyViolationError, "refusal", "The provider refused this request"),
            (litellm.AuthenticationError, "auth", "API key rejected by the provider"),
            (litellm.PermissionDeniedError, "auth", "API key lacks permission (or no credit)"),
            (
                litellm.RateLimitError,
                "rate_limit",
                "Rate limited by the provider; try again shortly",
            ),
            (litellm.Timeout, "timeout", "The model took too long to respond"),
            (litellm.BadRequestError, "bad_request", "The provider rejected the request"),
            (litellm.APIConnectionError, "provider_error", "Could not reach the model provider"),
        ]
        for exc_type, kind, summary in checks:
            if isinstance(exc, exc_type):
                return LLMError(kind, summary, entry.id, detail)
        return LLMError("provider_error", "Model call failed", entry.id, detail)

    def _redact(self, text: str) -> str:
        """Belt and braces: never let an API key leak into an error message or log."""
        for entry in self._catalog.list():
            if key := self._catalog.api_key(entry):
                text = text.replace(key, "***")
        return text
