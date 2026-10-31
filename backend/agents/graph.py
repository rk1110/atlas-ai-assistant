"""Builds the single-agent graph (see agents/__init__.py). The team version is team.py.

START ─▶ assistant ──tool calls?──▶ tools ──writes?──▶ approval ─▶ act ─┐
            ▲   │ no: final answer ─▶ END     │ no                       │
            └───┴──────────────────────────────┴──────────────────────────┘
"""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import get_runtime

from agents.assistant import AssistantAgent
from agents.nodes import approval_node, emit, make_act_node, make_tools_node
from agents.state import GraphState, RunContext
from core.interfaces.agent import AgentState
from core.interfaces.tool import Tool
from core.llm import ChatMessage


def build_graph(
    assistant: AssistantAgent,
    tools: list[Tool],
    checkpointer: BaseCheckpointSaver,
    max_model_calls: int,
) -> CompiledStateGraph:
    async def assistant_node(state: GraphState) -> dict[str, Any]:
        context = get_runtime(RunContext).context
        agent_state = AgentState(
            conversation_id=state["conversation_id"],
            messages=[ChatMessage(**m) for m in state["messages"]],
            scratch={
                "model_id": state["model_id"],
                "memory": state.get("memory", "(nothing yet)"),
                "model_calls": state["model_calls"],
                "trace": context.trace,
            },
        )
        result = await assistant.run(agent_state, emit)
        context.completions.append(result["completion"])
        return {
            "messages": [result["message"].model_dump()],
            "model_calls": state["model_calls"] + 1,
        }

    def after_assistant(state: GraphState) -> str:
        has_calls = bool(state["messages"] and state["messages"][-1].get("tool_calls"))
        return "tools" if has_calls and state["model_calls"] < max_model_calls else END

    def after_tools(state: GraphState) -> str:
        return "approval" if state["pending"] else "assistant"

    graph = StateGraph(GraphState, context_schema=RunContext)
    graph.add_node("assistant", assistant_node)
    graph.add_node("tools", make_tools_node(tools))
    graph.add_node("approval", approval_node)
    graph.add_node("act", make_act_node(tools))
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", after_assistant, ["tools", END])
    graph.add_conditional_edges("tools", after_tools, ["approval", "assistant"])
    graph.add_edge("approval", "act")
    graph.add_edge("act", "assistant")
    return graph.compile(checkpointer=checkpointer)
