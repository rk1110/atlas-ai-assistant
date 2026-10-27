"""Observability: every request becomes a Langfuse *trace* (principle 6).

A trace is the timeline of one request. Inside it are *observations*:
- a span:       a unit of work, e.g. "chat_turn" (later: "retrieve", "agent:planner")
- a generation: one LLM call, with model, input, output, tokens, cost and latency

    trace: chat_turn  (session = conversation id)
      └── generation: chat  (gpt-oss:120b, 208 in / 53 out tokens, 819 ms to first token)

This module wraps the Langfuse SDK the same way core/llm.py wraps LiteLLM: nothing else in
Atlas imports `langfuse`. Two rules shape the code:
1. Tracing must never break the app. If keys are missing, Langfuse is down, or the SDK raises,
   these wrappers log a warning and do nothing; the chat keeps working.
2. Parent/child links are explicit (`parent.generation(...)`), not "current span" context
   magic, because streaming generators pause at every `yield`, where implicit context breaks.
"""

import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from langfuse import Langfuse, propagate_attributes

from core.config import get_settings

logger = logging.getLogger(__name__)


class Generation:
    """One LLM call inside a trace. A no-op when tracing is off."""

    def __init__(self, observation: Any | None):
        self._obs = observation

    def first_token(self) -> None:
        """Record time-to-first-token: Langfuse shows it as 'completion start'."""
        self._safe("update", completion_start_time=datetime.now(UTC))

    def finish(
        self,
        *,
        output: Any,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float | None,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._safe(
            "update",
            output=output,
            usage_details={"input": input_tokens, "output": output_tokens},
            # Our own cost (from LiteLLM's price map), so Langfuse doesn't need its own prices.
            cost_details={"total": cost_usd} if cost_usd is not None else None,
            metadata=metadata,
            level="ERROR" if error else None,
            status_message=error,
        )
        self._safe("end")

    def fail(self, message: str) -> None:
        self._safe("update", level="ERROR", status_message=message)
        self._safe("end")

    def _safe(self, method: str, **kwargs: Any) -> None:
        if self._obs is None:
            return
        try:
            getattr(self._obs, method)(**{k: v for k, v in kwargs.items() if v is not None})
        except Exception:  # rule 1: tracing never breaks the app
            logger.warning("tracing: generation.%s failed", method, exc_info=True)


class Span:
    """A unit of work (the root of a trace, or a step inside one). A no-op when tracing is off."""

    def __init__(self, observation: Any | None, attributes: dict[str, Any]):
        self._obs = observation
        self._attributes = attributes  # trace-level fields, re-applied to every child

    @property
    def trace_id(self) -> str | None:
        return getattr(self._obs, "trace_id", None)

    def generation(
        self,
        name: str,
        *,
        model: str,
        input: Any,
        model_parameters: dict[str, Any] | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generation:
        if self._obs is None:
            return Generation(None)
        try:
            with propagate_attributes(**self._attributes):
                obs = self._obs.start_observation(
                    name=name,
                    as_type="generation",
                    model=model,
                    input=input,
                    model_parameters=_scalar_params(model_parameters or {}),
                    version=version,  # the prompt version, e.g. "chat_system@v1"
                    metadata=metadata,
                )
            return Generation(obs)
        except Exception:  # rule 1
            logger.warning("tracing: could not start generation", exc_info=True)
            return Generation(None)

    def finish(self, *, output: Any = None, error: str | None = None) -> None:
        if self._obs is None:
            return
        try:
            if error:
                self._obs.update(output=output, level="ERROR", status_message=error)
            elif output is not None:
                self._obs.update(output=output)
            self._obs.end()
        except Exception:  # rule 1
            logger.warning("tracing: could not finish span", exc_info=True)


class Tracer:
    def __init__(self, client: Langfuse | None, ui_url: str, project_id: str):
        self._client = client
        self._ui_url = ui_url.rstrip("/")
        self._project_id = project_id

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def start_trace(
        self,
        name: str,
        *,
        input: Any = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new trace. `session_id` groups traces: we use the conversation id, so
        Langfuse's Sessions view shows a whole conversation turn by turn."""
        attributes = {"trace_name": name, "session_id": session_id, "tags": tags}
        attributes = {k: v for k, v in attributes.items() if v is not None}
        if self._client is None:
            return Span(None, attributes)
        try:
            with propagate_attributes(**attributes):
                obs = self._client.start_observation(name=name, input=input, metadata=metadata)
            return Span(obs, attributes)
        except Exception:  # rule 1
            logger.warning("tracing: could not start trace", exc_info=True)
            return Span(None, attributes)

    def trace_url(self, trace_id: str | None) -> str | None:
        """Link to the trace in the Langfuse UI, for logs and the UI's 'view trace' link."""
        if not trace_id:
            return None
        return f"{self._ui_url}/project/{self._project_id}/traces/{trace_id}"

    def flush(self) -> None:
        """Send buffered spans now. Spans are exported in the background in batches, so
        short-lived scripts (smoke test, evals) must flush before exiting or lose traces."""
        if self._client is not None:
            try:
                self._client.flush()
            except Exception:  # rule 1
                logger.warning("tracing: flush failed", exc_info=True)


def _scalar_params(params: dict[str, Any]) -> dict[str, Any]:
    """Langfuse model_parameters accept only scalars and string lists."""
    return {k: v for k, v in params.items() if isinstance(v, str | int | float | bool)}


@lru_cache
def get_tracer() -> Tracer:
    settings = get_settings()
    client: Langfuse | None = None
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            host=settings.langfuse_host,
            environment=settings.langfuse_environment,
        )
    else:
        logger.warning("tracing disabled: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set")
    return Tracer(client, settings.langfuse_ui_url, settings.langfuse_project_id)
