"""Graph building blocks shared by the single agent (graph.py) and the team (team.py).

    make_tools_node     run read-only tools now; queue write tools for approval
    approval_node       PAUSE (interrupt) once per queued write; no side effects
    make_act_node       run the approved writes exactly once, record rejections

The one rule that shapes these: when a paused graph is resumed, LangGraph re-runs the node
that paused FROM THE START. So the node that calls `interrupt()` must have no side effects,
or a resumed run would do them twice. Approved writes happen in the next node (act).

Each builder takes `key`: the state list holding the conversation it works on ("messages"
for the single agent; "work" for the team, where each specialist has its own scratchpad).
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from pydantic import ValidationError

from core.events import StreamEvent, ToolCallEvent
from core.interfaces.retriever import Chunk
from core.interfaces.tool import Tool, ToolArgumentError, ToolResult
from core.llm import ChatMessage, ToolCall
from services.grounding import format_sources, source_label

TOOL_OUTPUT_CHARS = 4000  # what one tool result may add to the prompt

Node = Callable[[Any], Awaitable[dict[str, Any]]]


def make_tools_node(tools: list[Tool], key: str = "messages") -> Node:
    by_name = {t.name: t for t in tools}

    async def tools_node(state: Any) -> dict[str, Any]:
        """Run read-only tools now; queue write tools for the approval node."""
        last = state[key][-1] if state[key] else {}
        calls = [ToolCall(**c) for c in last.get("tool_calls") or []]
        messages: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for call in calls:
            tool = by_name.get(call.name)
            if tool is None:  # e.g. a specialist calling a tool it wasn't given
                messages.append(tool_message(call, ToolResult(ok=False, error="Unknown tool.")))
                continue
            try:
                args = tool.parse_arguments(call.arguments)
            except ToolArgumentError as exc:  # the model sees the error and can fix its call
                result = ToolResult(ok=False, error=f"Invalid arguments: {exc}")
                await emit_call(call, tool, "failed", None, result.error)
                messages.append(tool_message(call, result))
                continue
            if tool.requires_approval:
                pending.append(
                    {"call": call.model_dump(), "args": args.model_dump(),
                     "summary": tool.describe_call(args)}
                )  # fmt: skip
                continue
            summary = tool.describe_call(args)
            await emit_call(call, tool, "started", summary)
            result = await tool.run(args)
            first_number = len(state["sources"]) + len(sources) + 1
            new_sources, content = render_result(result, first_number)
            sources += new_sources
            status = "completed" if result.ok else "failed"
            await emit_call(call, tool, status, summary, result.error, preview(result, new_sources))
            messages.append(
                ChatMessage(role="tool", content=content, tool_call_id=call.id).model_dump()
            )
        return {key: messages, "sources": sources, "pending": pending}

    return tools_node


def approval_node(state: Any) -> dict[str, Any]:
    """Pause once per write call. On resume, `interrupt()` returns the human's decision.
    No side effects here (see module docstring)."""
    decisions = []
    for item in state["pending"]:
        call = ToolCall(**item["call"])
        answer = interrupt(
            {
                "approval_id": call.id,
                "tool_name": call.name,
                "summary": item["summary"],
                "payload": item["args"],
            }
        )
        decisions.append({**item, "answer": answer})
    return {"decisions": decisions, "pending": []}


def make_act_node(tools: list[Tool], key: str = "messages") -> Node:
    by_name = {t.name: t for t in tools}

    async def act_node(state: Any) -> dict[str, Any]:
        """Run approved writes (exactly once), record rejections."""
        messages = []
        for item in state["decisions"]:
            call, tool = ToolCall(**item["call"]), by_name[item["call"]["name"]]
            answer = item["answer"] or {}
            if answer.get("decision") != "approve":
                error = "Rejected by the user. It was NOT done; do not retry."
                await emit_call(call, tool, "failed", item["summary"], error)
                messages.append(tool_message(call, ToolResult(ok=False, error=error)))
                continue
            try:  # the human may have edited the arguments on the approval card
                args = tool.parse_arguments(answer.get("args") or item["args"])
            except ToolArgumentError as exc:
                error = f"The edited arguments were invalid ({exc}). Not done."
                await emit_call(call, tool, "failed", item["summary"], error)
                messages.append(tool_message(call, ToolResult(ok=False, error=error)))
                continue
            summary = tool.describe_call(args)
            await emit_call(call, tool, "started", summary)
            result = await tool.run(args)
            await emit_call(call, tool, "completed" if result.ok else "failed", summary,
                            result.error, result.output)  # fmt: skip
            messages.append(tool_message(call, result))
        return {key: messages, "decisions": []}

    return act_node


async def emit(event: StreamEvent) -> None:
    """Send an event to the UI: LangGraph's custom stream, read by agents/runner.py."""
    get_stream_writer()(event.model_dump())


async def emit_call(
    call: ToolCall,
    tool: Tool,
    status: str,
    summary: str | None,
    error: str | None = None,
    output: Any = None,
) -> None:
    await emit(
        ToolCallEvent(
            call_id=call.id, tool_name=tool.name, status=status, summary=summary,  # type: ignore[arg-type]
            input=call.arguments, output=output, error=error,
        )
    )  # fmt: skip


def render_result(result: ToolResult, first_number: int) -> tuple[list[dict[str, Any]], str]:
    """Tool result -> (new sources, text for the model). Retrieval results are numbered
    continuing from earlier searches, so [n] stays unique across the whole turn."""
    if not result.ok:
        return [], f"Error: {result.error}"
    output = result.output if isinstance(result.output, dict) else {"result": result.output}
    chunks = [Chunk(**c) for c in output.get("chunks", [])]
    if "chunks" not in output:
        return [], json.dumps(output)[:TOOL_OUTPUT_CHARS]
    if not chunks:
        return [], output.get("note", "No results.")
    text = format_sources(chunks, start=first_number)
    return [c.model_dump() for c in chunks], text[:TOOL_OUTPUT_CHARS]


def preview(result: ToolResult, sources: list[dict[str, Any]]) -> Any:
    """What the UI shows as the tool's output: titles for searches, the output otherwise."""
    if sources:
        return [source_label(Chunk(**s)) for s in sources]
    return result.output


def tool_message(call: ToolCall, result: ToolResult) -> dict[str, Any]:
    content = json.dumps(result.output) if result.ok else f"Error: {result.error}"
    message = ChatMessage(role="tool", content=content[:TOOL_OUTPUT_CHARS], tool_call_id=call.id)
    return message.model_dump()


def first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    location = ".".join(str(p) for p in err["loc"])
    return f"{location}: {err['msg']}" if location else err["msg"]
