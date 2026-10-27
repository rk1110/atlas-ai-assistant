"""Show the prompt registry and the StreamEvent contract in action (no LLM calls, free).

docker compose exec backend python -m scripts.show_events
"""

from datetime import date

from api.deps import get_prompts, get_settings
from core.events import (
    AgentStepEvent,
    ApprovalRequestEvent,
    CitationEvent,
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    TokenEvent,
    ToolCallEvent,
    Usage,
    stream_event_adapter,
    to_sse,
)


def show_prompt() -> None:
    prompt = get_prompts().render(
        "chat_system", assistant_name=get_settings().assistant_name, today=date.today().isoformat()
    )
    print(f"### Prompt {prompt.ref}\n{prompt.text}")


def show_events() -> None:
    usage = Usage(
        model_id="gpt-oss-cloud",
        input_tokens=92,
        output_tokens=62,
        cost_usd=0.0,
        latency_ms=1055,
        time_to_first_token_ms=652,
    )
    examples: list[StreamEvent] = [
        TokenEvent(text="Atlas was a Titan"),
        CitationEvent(
            citation_id="1",
            document_id="acme-leave-policy",
            title="Leave policy",
            snippet="Employees receive 16 weeks of paid parental leave.",
        ),
        AgentStepEvent(step_id="s1", agent="researcher", status="started", title="Searching"),
        ToolCallEvent(
            call_id="c1",
            tool_name="search_docs",
            status="started",
            input={"query": "parental leave"},
        ),
        ApprovalRequestEvent(
            approval_id="a1",
            tool_name="create_ticket",
            summary="Create HR ticket",
            payload={"project": "HR"},
        ),
        ErrorEvent(code="rate_limit", message="Rate limited; try again shortly", retryable=True),
        DoneEvent(message_id="m1", usage=usage, prompt_ref="chat_system@v1"),
    ]
    print("\n### The 7 events, exactly as sent over SSE")
    for event in examples:
        print(to_sse(event), end="")

    # Round trip: the frontend sends JSON; the discriminated union picks the right class.
    raw = '{"type": "token", "text": "hi"}'
    parsed = stream_event_adapter.validate_json(raw)
    print(f"### Parsing {raw!r} -> {type(parsed).__name__}")
    try:
        stream_event_adapter.validate_json('{"type": "token"}')
    except Exception as err:  # noqa: BLE001 - demo: show the validation message
        print(f"### Invalid event rejected: {str(err).splitlines()[0]}")


if __name__ == "__main__":
    show_prompt()
    show_events()
