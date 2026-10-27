"""The streaming event contract between backend and frontend (principle 4).

Every chat response is a stream of these events, sent over Server-Sent Events (SSE).
The frontend's `lib/events.ts` mirrors this file EXACTLY: same `type` strings, same field names.

Why define all seven now, when Phase 1 only sends `token`, `error` and `done`:
the UI's citation chips (Phase 2), agent panel (Phase 4-5) and approval cards (Phase 4) all
consume this same stream. Fixing the contract on day one means later phases only *emit* new
events; nothing gets rewired. Adding an optional field later is safe; renaming or removing a
field is a breaking change for the frontend.

Each event is a Pydantic model with a literal `type` field. `StreamEvent` is a *discriminated
union*: Pydantic (and TypeScript, on the frontend) look at `type` to know which shape the
rest of the JSON has.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

# ---------------------------------------------------------------- Phase 1: used now


class TokenEvent(BaseModel):
    """A chunk of the assistant's answer text. The UI appends these as they arrive."""

    type: Literal["token"] = "token"
    text: str


ErrorCode = Literal[
    # Model/provider problems (mirrors core.llm.LLMErrorKind; a test keeps them in sync)
    "unknown_model", "unavailable", "auth", "rate_limit", "bad_request",
    "context_too_long", "refusal", "timeout", "billing", "invalid_output", "provider_error",
    # Atlas's own problems
    "validation", "internal",
]  # fmt: skip


class ErrorEvent(BaseModel):
    """Something failed. Usually the last event before `done` (or instead of it)."""

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str  # safe to show to the user: never contains secrets or stack traces
    retryable: bool  # lets the UI offer a "Try again" button only when it can help


class Usage(BaseModel):
    """What one assistant reply cost. Feeds the Analytics page (Phase 3/7)."""

    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: int
    time_to_first_token_ms: int | None


class DoneEvent(BaseModel):
    """Always the final event of a stream. Tells the UI to stop the spinner."""

    type: Literal["done"] = "done"
    message_id: str | None  # id of the saved assistant message (None if nothing was saved)
    usage: Usage | None = None  # None when the call failed before the model answered
    prompt_ref: str | None = None  # which prompt produced the answer, e.g. "chat_system@v1"
    trace_id: str | None = None  # Langfuse trace id (step 5), for "view trace" links


# ---------------------------------------------------------------- Phase 2+: defined now, used later


class CitationEvent(BaseModel):
    """A source the answer relies on (Phase 2 RAG). Rendered as a clickable chip."""

    type: Literal["citation"] = "citation"
    citation_id: str  # referenced in the answer text, e.g. "[1]"
    document_id: str
    title: str
    url: str | None = None
    snippet: str  # the exact passage that supports the answer
    score: float | None = None  # retrieval relevance score (shown in debug views)


StepStatus = Literal["started", "completed", "failed"]


class AgentStepEvent(BaseModel):
    """An agent started or finished a step (Phase 4-5). Drives the live agent panel."""

    type: Literal["agent_step"] = "agent_step"
    step_id: str  # "started" and "completed" events for one step share this id
    agent: str  # e.g. "planner", "researcher", "action", "verifier"
    status: StepStatus
    title: str  # short, human-readable: "Searching the handbook"
    detail: str | None = None


class ToolCallEvent(BaseModel):
    """An agent called a tool (Phase 4). The UI shows input and output in the step timeline."""

    type: Literal["tool_call"] = "tool_call"
    call_id: str
    tool_name: str
    status: StepStatus
    input: dict[str, Any]
    output: Any | None = None  # set when status == "completed"
    error: str | None = None  # set when status == "failed"


class ApprovalRequestEvent(BaseModel):
    """The agent wants to write to an external system and needs a human yes/no (Phase 4).

    Any tool that writes to Jira, Slack, email, etc. MUST emit this and wait for approval.
    """

    type: Literal["approval_request"] = "approval_request"
    approval_id: str
    tool_name: str
    summary: str  # e.g. "Create Jira ticket HR-123: Confirm parental leave dates"
    payload: dict[str, Any]  # the exact arguments that will be sent if approved


# ---------------------------------------------------------------- The union + SSE encoding

StreamEvent = Annotated[
    TokenEvent
    | CitationEvent
    | AgentStepEvent
    | ToolCallEvent
    | ApprovalRequestEvent
    | ErrorEvent
    | DoneEvent,
    Field(discriminator="type"),
]

# A TypeAdapter validates/serializes a type that isn't a BaseModel subclass (like this union).
stream_event_adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)

RETRYABLE_CODES: frozenset[str] = frozenset({"rate_limit", "timeout", "provider_error"})


def to_sse(event: StreamEvent) -> str:
    """Encode one event in the SSE wire format: a `data:` line, then a blank line.

    SSE is plain text over a long-lived HTTP response. Each message is one or more
    `field: value` lines terminated by an empty line. We put the whole event (including
    `type`) in a single JSON `data:` line, so the frontend parser has exactly one job:
    split on blank lines, JSON-parse each `data:`, switch on `type`.
    """
    return f"data: {event.model_dump_json()}\n\n"
