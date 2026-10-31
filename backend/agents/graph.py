"""Builds the agent graph: nodes, edges, and the approval interrupt (see agents/__init__.py).

The one rule that shapes this file: when a paused graph is resumed, LangGraph re-runs the
node that paused FROM THE START. So the node that calls `interrupt()` (approval) must have no
side effects, or a resumed run would do them twice. Approved writes happen in the next
node (act), which runs exactly once.
"""

import json
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import get_runtime
from langgraph.types import interrupt
from pydantic import ValidationError

from agents.assistant import AssistantAgent
from agents.state import GraphState, RunContext
from core.events import StreamEvent, ToolCallEvent
from core.interfaces.agent import AgentState
from core.interfaces.retriever import Chunk
from core.interfaces.tool import Tool, ToolResult
from core.llm import ChatMessage, ToolCall
from services.grounding import format_sources, source_label

TOOL_OUTPUT_CHARS = 4000  # what one tool result may add to the prompt


def build_graph(
    assistant: AssistantAgent,
    tools: list[Tool],
    checkpointer: BaseCheckpointSaver,
    max_model_calls: int,
) -> CompiledStateGraph:
    by_name = {t.name: t for t in tools}

    async def assistant_node(state: GraphState) -> dict[str, Any]:
        context = get_runtime(RunContext).context
        agent_state = AgentState(
            conversation_id=state["conversation_id"],
            messages=[ChatMessage(**m) for m in state["messages"]],
            scratch={
                "model_id": state["model_id"],
                "model_calls": state["model_calls"],
                "trace": context.trace,
            },
        )
        result = await assistant.run(agent_state, _emit)
        context.completions.append(result["completion"])
        return {
            "messages": [result["message"].model_dump()],
            "model_calls": state["model_calls"] + 1,
        }

    async def tools_node(state: GraphState) -> dict[str, Any]:
        """Run read-only tools now; queue write tools for the approval node."""
        calls = _last_tool_calls(state)
        messages: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for call in calls:
            tool = by_name.get(call.name)
            if tool is None:
                messages.append(_tool_message(call, ToolResult(ok=False, error="Unknown tool.")))
                continue
            try:
                args = tool.input_model.model_validate(call.arguments)
            except ValidationError as exc:  # the model sees the error and can fix its call
                result = ToolResult(ok=False, error=f"Invalid arguments: {_first_error(exc)}")
                await _emit_call(call, tool, "failed", None, result.error)
                messages.append(_tool_message(call, result))
                continue
            if tool.requires_approval:
                pending.append(
                    {"call": call.model_dump(), "args": args.model_dump(),
                     "summary": tool.describe_call(args)}
                )  # fmt: skip
                continue
            await _emit_call(call, tool, "started", tool.describe_call(args))
            result = await tool.run(args)
            first_number = len(state["sources"]) + len(sources) + 1
            new_sources, content = _render_result(result, first_number)
            sources += new_sources
            status = "completed" if result.ok else "failed"
            summary = tool.describe_call(args)
            preview = _preview(result, new_sources)
            await _emit_call(call, tool, status, summary, result.error, preview)
            messages.append(
                ChatMessage(role="tool", content=content, tool_call_id=call.id).model_dump()
            )
        return {"messages": messages, "sources": sources, "pending": pending}

    def approval_node(state: GraphState) -> dict[str, Any]:
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

    async def act_node(state: GraphState) -> dict[str, Any]:
        """Run approved writes (exactly once), record rejections."""
        messages = []
        for item in state["decisions"]:
            call, tool = ToolCall(**item["call"]), by_name[item["call"]["name"]]
            answer = item["answer"] or {}
            if answer.get("decision") != "approve":
                error = "Rejected by the user. It was NOT done; do not retry."
                await _emit_call(call, tool, "failed", item["summary"], error)
                messages.append(_tool_message(call, ToolResult(ok=False, error=error)))
                continue
            try:  # the human may have edited the arguments on the approval card
                args = tool.input_model.model_validate(answer.get("args") or item["args"])
            except ValidationError as exc:
                error = f"The edited arguments were invalid ({_first_error(exc)}). Not done."
                await _emit_call(call, tool, "failed", item["summary"], error)
                messages.append(_tool_message(call, ToolResult(ok=False, error=error)))
                continue
            summary = tool.describe_call(args)
            await _emit_call(call, tool, "started", summary)
            result = await tool.run(args)
            await _emit_call(call, tool, "completed" if result.ok else "failed", summary,
                             result.error, result.output)  # fmt: skip
            messages.append(_tool_message(call, result))
        return {"messages": messages, "decisions": []}

    def after_assistant(state: GraphState) -> str:
        has_calls = bool(state["messages"] and state["messages"][-1].get("tool_calls"))
        return "tools" if has_calls and state["model_calls"] < max_model_calls else END

    def after_tools(state: GraphState) -> str:
        return "approval" if state["pending"] else "assistant"

    graph = StateGraph(GraphState, context_schema=RunContext)
    graph.add_node("assistant", assistant_node)
    graph.add_node("tools", tools_node)
    graph.add_node("approval", approval_node)
    graph.add_node("act", act_node)
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", after_assistant, ["tools", END])
    graph.add_conditional_edges("tools", after_tools, ["approval", "assistant"])
    graph.add_edge("approval", "act")
    graph.add_edge("act", "assistant")
    return graph.compile(checkpointer=checkpointer)


async def _emit(event: StreamEvent) -> None:
    """Send an event to the UI: LangGraph's custom stream, read by agents/runner.py."""
    get_stream_writer()(event.model_dump())


async def _emit_call(
    call: ToolCall,
    tool: Tool,
    status: str,
    summary: str | None,
    error: str | None = None,
    output: Any = None,
) -> None:
    await _emit(
        ToolCallEvent(
            call_id=call.id, tool_name=tool.name, status=status, summary=summary,  # type: ignore[arg-type]
            input=call.arguments, output=output, error=error,
        )
    )  # fmt: skip


def _last_tool_calls(state: GraphState) -> list[ToolCall]:
    last = state["messages"][-1] if state["messages"] else {}
    return [ToolCall(**c) for c in last.get("tool_calls") or []]


def _render_result(result: ToolResult, first_number: int) -> tuple[list[dict[str, Any]], str]:
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


def _preview(result: ToolResult, sources: list[dict[str, Any]]) -> Any:
    """What the UI shows as the tool's output: titles for searches, the output otherwise."""
    if sources:
        return [source_label(Chunk(**s)) for s in sources]
    return result.output


def _tool_message(call: ToolCall, result: ToolResult) -> dict[str, Any]:
    content = json.dumps(result.output) if result.ok else f"Error: {result.error}"
    message = ChatMessage(role="tool", content=content[:TOOL_OUTPUT_CHARS], tool_call_id=call.id)
    return message.model_dump()


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    location = ".".join(str(p) for p in err["loc"])
    return f"{location}: {err['msg']}" if location else err["msg"]
