"""The LLM gateway: the ONLY place in Atlas that calls a language model (principle 2).

Every model call goes through `LLMGateway`, which wraps LiteLLM. LiteLLM gives one
OpenAI-style interface over many providers (Anthropic, Ollama, OpenAI, ...), so switching
models is a config change in `config/models.yaml`, never a code change.

Owning this single choke point is what makes cross-cutting features cheap:
- every call is traced in Langfuse here, once (step 5);
- every call is recorded in the usage ledger, and refused once the budget is spent (Phase 7B);
- Phase 7 adds caching and routing here, once.

Three kinds of call:
- `stream_chat`: free text, streamed as `TextDelta`s then one `Completion` (the chat UI)
- `complete_structured`: JSON that must match a Pydantic schema (classification, judging)
- `complete_with_tools`: the model may answer, or ask us to run tools (the agent, Phase 4)
"""

import asyncio
import json
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

# Use the price/capability map bundled with the pinned LiteLLM version instead of downloading
# the latest one from GitHub at import time: reproducible costs, works offline, no runtime fetch.
# Must be set before `import litellm`.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm
from pydantic import BaseModel, Field, ValidationError

from core.model_catalog import ModelCatalog, ModelEntry
from core.tracing import Generation, Span, Tracer
from core.usage import UsageLedger

litellm.suppress_debug_info = True  # LiteLLM otherwise prints help banners on every error


class ToolCall(BaseModel):
    """The model asking us to run a tool. It never runs anything itself."""

    id: str  # the provider's id; the tool's result must quote it back (tool_call_id)
    name: str
    arguments: dict[str, Any]  # parsed from the JSON string the model wrote


class ImagePart(BaseModel):
    """An image sent with a message (Phase 6): the raw bytes, base64-encoded, and their type.

    Vision models read images as tokens too: an image is cut into patches, and each patch
    costs roughly as much as a word or two, so a screenshot adds a few hundred input tokens.
    """

    media_type: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    data: str  # base64, without the "data:...;base64," prefix

    def data_url(self) -> str:
        return f"data:{self.media_type};base64,{self.data}"


class ChatMessage(BaseModel):
    """One message in a conversation, in the role/content shape every chat model accepts.

    Agents (Phase 4) add two shapes: an assistant message that carries `tool_calls`, and a
    `tool` message carrying one tool's result, linked to its call by `tool_call_id`.
    Phase 6 adds `images` on user messages, for vision models.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    images: list[ImagePart] | None = None


class ToolTurn(BaseModel):
    """Result of `complete_with_tools`: some text, and zero or more tool calls."""

    text: str
    tool_calls: list[ToolCall]
    completion: "Completion"


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
    cost_usd: float | None  # None when neither models.yaml nor LiteLLM has a price
    latency_ms: int
    time_to_first_token_ms: int | None  # None for non-streamed calls
    finish_reason: str | None  # "stop" = natural end, "length" = hit max_tokens
    trace_id: str | None = None  # Langfuse trace this call belongs to


LLMChunk = Annotated[TextDelta | Completion, Field(discriminator="type")]
ToolTurn.model_rebuild()

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
    "invalid_output",
    "provider_error",
    "budget",
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
    def __init__(self, catalog: ModelCatalog, tracer: Tracer, ledger: UsageLedger | None = None):
        self._catalog = catalog
        self._tracer = tracer
        self._ledger = ledger  # None in unit tests: no recording, no budget

    # ------------------------------------------------------------------ streaming text

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        *,
        trace: Span | None = None,
        name: str = "chat",
        prompt_ref: str | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Stream a chat completion: yields `TextDelta`s as they arrive, then one `Completion`.

        Why stream: a full answer takes seconds; streaming shows the first words after
        ~0.5-2 s instead of making the user stare at a spinner (time-to-first-token).

        `trace` is the caller's Langfuse span (e.g. the chat turn). Without one, the call gets
        its own trace, so even one-off scripts are traced.
        """
        entry = await self._usable_entry(model_id)
        self._check_images(entry, messages)
        own_trace = trace is None
        span = trace or self._tracer.start_trace(name, input=_dump_for_trace(messages))
        generation = self._start_generation(span, name, entry, messages, prompt_ref)

        started = time.perf_counter()
        first_token_at: float | None = None
        finish_reason: str | None = None
        usage: Any = None
        parts: list[str] = []
        try:
            response = await litellm.acompletion(
                messages=_dump(messages),
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
                            generation.first_token()
                        parts.append(text)
                        yield TextDelta(text=text)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
            if finish_reason == "content_filter":
                # LiteLLM maps Anthropic's `stop_reason: "refusal"` (safety classifier) to this.
                raise LLMError("refusal", "The model declined to answer this request.", entry.id)
        except LLMError as err:
            _record_failure(err, generation, span if own_trace else None)
            raise
        except (asyncio.CancelledError, GeneratorExit):
            # Caller stopped reading (client disconnected). Close the observation, don't hide it.
            generation.fail("cancelled by caller")
            if own_trace:
                span.finish(error="cancelled")
            raise
        except Exception as exc:
            err = self._translate_error(exc, entry)
            _record_failure(err, generation, span if own_trace else None)
            raise err from exc

        completion = self._completion(
            entry, usage, finish_reason, started, first_token_at, span.trace_id
        )
        self._finish_generation(generation, "".join(parts), completion, prompt_ref)
        await self._record(name, completion)
        if own_trace:
            span.finish(output="".join(parts))
        yield completion

    # ------------------------------------------------------------------ structured output

    async def complete_structured[T: BaseModel](
        self,
        model_id: str,
        messages: list[ChatMessage],
        schema: type[T],
        *,
        trace: Span | None = None,
        name: str = "structured",
        prompt_ref: str | None = None,
    ) -> tuple[T, Completion]:
        """Ask for JSON matching `schema`; return it parsed and validated.

        Two ways to get structured output, chosen per model in models.yaml:
        - native: the JSON Schema is sent with the request and the provider *constrains
          generation*: at each step only tokens that keep the output valid are allowed.
          (Claude; local Ollama.)
        - prompt: the provider ignores schemas (Ollama Cloud, tested 2026-10-27), so the schema
          goes into the system prompt and we rely on the model following it.
        Either way we validate with Pydantic. On invalid output we retry once, showing the model
        its own reply and the exact validation error: models are good at fixing a named mistake.
        """
        entry = await self._usable_entry(model_id)
        self._check_images(entry, messages)
        own_trace = trace is None
        span = trace or self._tracer.start_trace(name, input=_dump_for_trace(messages))
        native = entry.structured_output == "native"
        conversation = list(messages) if native else _with_schema_instructions(messages, schema)
        extra = {"response_format": schema} if native else {}

        started = time.perf_counter()
        input_tokens = output_tokens = 0
        cost: float | None = 0.0
        error: LLMError | None = None
        for attempt in range(1, STRUCTURED_ATTEMPTS + 1):
            generation = self._start_generation(
                span, name, entry, conversation, prompt_ref, attempt=attempt
            )
            try:
                response = await litellm.acompletion(
                    messages=_dump(conversation), **extra, **self._call_kwargs(entry)
                )
            except Exception as exc:
                err = self._translate_error(exc, entry)
                _record_failure(err, generation, span if own_trace else None)
                raise err from exc

            choice = response.choices[0]
            content = choice.message.content or ""
            call_in, call_out = _token_counts(response.usage)
            call_cost = _cost(entry, call_in, call_out)
            if self._ledger:  # every attempt is billed, including the ones we retry
                await self._ledger.record(entry.id, name, call_in, call_out, call_cost)
            input_tokens, output_tokens = input_tokens + call_in, output_tokens + call_out
            cost = None if cost is None or call_cost is None else cost + call_cost

            try:
                parsed = schema.model_validate_json(_extract_json(content))
            except ValidationError as exc:
                problem = _first_problem(exc)
                error = LLMError(
                    "invalid_output",
                    "The model's answer didn't match the expected format.",
                    entry.id,
                    f"attempt {attempt}: {problem} in {content[:200]!r}",
                )
                generation.finish(
                    output=content, input_tokens=call_in, output_tokens=call_out,
                    cost_usd=call_cost, error=f"invalid output: {problem}",
                )  # fmt: skip
                conversation = [
                    *conversation,
                    ChatMessage(role="assistant", content=content),
                    ChatMessage(
                        role="user",
                        content=f"That reply was not valid ({problem}). "
                        "Reply again with only the JSON object.",
                    ),
                ]
                continue

            completion = Completion(
                model_id=entry.id,
                litellm_model=entry.litellm_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=round((time.perf_counter() - started) * 1000),
                time_to_first_token_ms=None,
                finish_reason=choice.finish_reason,
                trace_id=span.trace_id,
            )
            generation.finish(
                output=parsed.model_dump(), input_tokens=call_in, output_tokens=call_out,
                cost_usd=call_cost, metadata={"prompt_ref": prompt_ref, "attempt": attempt},
            )  # fmt: skip
            if own_trace:
                span.finish(output=parsed.model_dump())
            return parsed, completion

        assert error is not None
        if own_trace:
            span.finish(error=error.message)
        raise error

    # ------------------------------------------------------------------ tool calling

    async def complete_with_tools(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        trace: Span | None = None,
        name: str = "agent",
        prompt_ref: str | None = None,
    ) -> ToolTurn:
        """One agent step: send the conversation plus tool definitions; get back text and/or
        tool calls. Not streamed: the agent needs the whole decision before it can act.

        `tools` are OpenAI-style function definitions (name, description, JSON Schema of the
        arguments); LiteLLM translates them for each provider. Arguments come back as a JSON
        *string* written by the model, so they can be invalid: unparseable ones are passed on
        as {"_invalid_json": ...}, and the tool's schema validation reports the problem to
        the model as an error it can fix.
        """
        entry = await self._usable_entry(model_id)
        self._check_images(entry, messages)
        own_trace = trace is None
        span = trace or self._tracer.start_trace(name, input=_dump_for_trace(messages))
        generation = self._start_generation(span, name, entry, messages, prompt_ref)
        started = time.perf_counter()
        try:
            response = await litellm.acompletion(
                messages=_dump(messages), tools=tools, **self._call_kwargs(entry)
            )
        except Exception as exc:
            err = self._translate_error(exc, entry)
            _record_failure(err, generation, span if own_trace else None)
            raise err from exc

        choice = response.choices[0]
        calls = [_tool_call(c) for c in (choice.message.tool_calls or [])]
        text = choice.message.content or ""
        completion = self._completion(
            entry, response.usage, choice.finish_reason, started, None, span.trace_id
        )
        output = {"text": text, "tool_calls": [c.model_dump() for c in calls]}
        self._finish_generation(generation, output, completion, prompt_ref)
        await self._record(name, completion)
        if own_trace:
            span.finish(output=output)
        return ToolTurn(text=text, tool_calls=calls, completion=completion)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _check_images(entry: ModelEntry, messages: list[ChatMessage]) -> None:
        """A text-only model sent an image either errors or silently ignores it (and answers
        as if there were no image). Fail clearly instead; callers route images to a vision
        model (`defaults.vision`) before getting here."""
        if not entry.vision and any(m.images for m in messages):
            raise LLMError(
                "bad_request", f"{entry.label} can't read images. Pick a vision model.", entry.id
            )

    async def _usable_entry(self, model_id: str) -> ModelEntry:
        entry = self._catalog.get(model_id)
        if entry is None:
            raise LLMError("unknown_model", f"Unknown model '{model_id}'", model_id)
        availability = await self._catalog.availability(entry)
        if not availability.available:
            raise LLMError("unavailable", availability.reason or "Model unavailable", model_id)
        if self._ledger and (reason := await self._ledger.over_budget()):
            raise LLMError("budget", reason, model_id)
        return entry

    async def _record(self, purpose: str, completion: "Completion") -> None:
        if self._ledger:
            await self._ledger.record(
                completion.model_id,
                purpose,
                completion.input_tokens,
                completion.output_tokens,
                completion.cost_usd,
            )

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
    def _start_generation(
        span: Span,
        name: str,
        entry: ModelEntry,
        messages: list[ChatMessage],
        prompt_ref: str | None,
        attempt: int = 1,
    ) -> Generation:
        return span.generation(
            name,
            model=entry.litellm_model,
            input=_dump_for_trace(messages),
            model_parameters=entry.params,
            version=prompt_ref,
            metadata={
                "model_id": entry.id,
                "prompt_ref": prompt_ref,
                "provider": entry.provider,
                "attempt": attempt,
            },
        )

    @staticmethod
    def _finish_generation(
        generation: Generation, output: Any, completion: Completion, prompt_ref: str | None
    ) -> None:
        generation.finish(
            output=output,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cost_usd=completion.cost_usd,
            metadata={
                "prompt_ref": prompt_ref,
                "latency_ms": completion.latency_ms,
                "time_to_first_token_ms": completion.time_to_first_token_ms,
                "finish_reason": completion.finish_reason,
            },
        )

    @staticmethod
    def _completion(
        entry: ModelEntry,
        usage: Any,
        finish_reason: str | None,
        started: float,
        first_token_at: float | None,
        trace_id: str | None,
    ) -> Completion:
        input_tokens, output_tokens = _token_counts(usage)
        cost = _cost(entry, input_tokens, output_tokens)
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
            trace_id=trace_id,
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


STRUCTURED_ATTEMPTS = 2  # first try + one retry that shows the model its validation error


def _with_schema_instructions(
    messages: list[ChatMessage], schema: type[BaseModel]
) -> list[ChatMessage]:
    """Prompt-mode structured output: describe the JSON Schema in the system prompt."""
    instructions = (
        "\n\nRespond with ONLY a JSON object that matches this JSON Schema. "
        "No prose, no Markdown code fences.\n" + json.dumps(schema.model_json_schema())
    )
    if messages and messages[0].role == "system":
        first = ChatMessage(role="system", content=messages[0].content + instructions)
        return [first, *messages[1:]]
    return [ChatMessage(role="system", content=instructions.strip()), *messages]


def _extract_json(content: str) -> str:
    """Models in prompt mode often wrap JSON in ```json fences or add a sentence around it."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    first, last = content.find("{"), content.rfind("}")
    return content[first : last + 1] if first != -1 and last > first else content


def _first_problem(exc: ValidationError) -> str:
    """Short, model-readable description of what was wrong, e.g. "intent: Input should be..."."""
    err = exc.errors()[0]
    location = ".".join(str(part) for part in err["loc"])
    return f"{location}: {err['msg']}" if location else err["msg"]


def _token_counts(usage: Any) -> tuple[int, int]:
    return (getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)


def _cost(entry: ModelEntry, input_tokens: int, output_tokens: int) -> float | None:
    """Our price from models.yaml if set, else LiteLLM's bundled map; None when neither knows
    the model. (Ollama Cloud's free tier has no per-token price: None, shown as "no price".)"""
    if entry.pricing:
        return entry.pricing.cost(input_tokens, output_tokens)
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=entry.litellm_model, prompt_tokens=input_tokens, completion_tokens=output_tokens
        )
    except Exception:  # noqa: BLE001 - unknown price is a normal case, not an error
        return None
    return prompt_cost + completion_cost


def _record_failure(err: LLMError, generation: Generation, own_span: Span | None) -> None:
    """Mark the failed call in Langfuse (and close its trace if the gateway opened it)."""
    generation.fail(f"[{err.kind}] {err.detail or err.message}")
    if own_span is not None:
        own_span.finish(error=err.message)


def _dump(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Our messages in the OpenAI wire format LiteLLM expects (tool calls carry their
    arguments as a JSON string there)."""
    return [_wire(m) for m in messages]


def _wire(m: ChatMessage) -> dict[str, Any]:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
    if m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content or None,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in m.tool_calls
            ],
        }
    if m.images:
        # OpenAI-style content parts: the text, then each image as a data URL. LiteLLM turns
        # this into each provider's own format (Anthropic image blocks, Ollama's `images`).
        return {
            "role": m.role,
            "content": [
                {"type": "text", "text": m.content},
                *({"type": "image_url", "image_url": {"url": i.data_url()}} for i in m.images),
            ],
        }
    return {"role": m.role, "content": m.content}


def _dump_for_trace(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """What Langfuse records: the same messages, with each image replaced by a short note.
    A screenshot is hundreds of kilobytes of base64; traces stay readable and small."""
    dumped = []
    for m in messages:
        wire = _wire(m)
        if m.images:
            notes = [f"[image: {i.media_type}, {len(i.data) * 3 // 4096} KB]" for i in m.images]
            wire = {"role": m.role, "content": "\n".join([m.content, *notes])}
        dumped.append(wire)
    return dumped


def _tool_call(raw: Any) -> ToolCall:
    arguments = raw.function.arguments or "{}"
    try:
        parsed = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
    except json.JSONDecodeError:
        parsed = {"_invalid_json": arguments}
    if not isinstance(parsed, dict):
        parsed = {"_invalid_json": arguments}
    name = raw.function.name
    return ToolCall(id=raw.id or f"call_{name}", name=name, arguments=parsed)
