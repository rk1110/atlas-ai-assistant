"""The agent team (Phase 5): a Planner hands work to specialists, a Verifier checks the result.

    START ─▶ planner ─▶ dispatch ──step for──▶ researcher ⇄ research_tools ─┐
                          ▲   │                action ⇄ action_tools          │
                          │   │                   └─▶ approval ─▶ act ─┐      │
                          │   │            (finish_step: note the result)◀──┴──┘
                          │   └──all steps done──▶ writer ─▶ verifier ──approved──▶ END
                          │                          ▲            │ issues (once)
                          └──────────────────────────┴────────────┘

This is the *supervisor* pattern: one coordinator decides who works next; specialists
never call each other. The alternative, *handoffs*, lets each agent pass control directly
to another; it's more flexible, but harder to follow and to bound. Here the plan is made
once, up front, so the order of work is predictable and visible in the UI.

Why specialists at all, when one agent could hold every tool (Phase 4)? Each one gets a
focused prompt and only the tools it needs: the Researcher can't write anything, the
Action agent only acts. Smaller choices, fewer mistakes, easier to evaluate one by one.
The price: more model calls per request (measured by the agent evals).

Each specialist works in its own scratchpad: `work` is one append-only list, and
`work_start` marks where the current step began, so a specialist sees only its own task.
"""

import operator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import get_runtime

from agents.assistant import AssistantAgent
from agents.nodes import approval_node, emit, make_act_node, make_tools_node
from agents.state import RunContext
from agents.team_agents import PlannerAgent, VerifierAgent
from core.events import AgentStepEvent
from core.interfaces.agent import Agent, AgentState
from core.interfaces.retriever import Chunk
from core.interfaces.tool import Tool
from core.llm import ChatMessage
from services.grounding import format_sources

MAX_REVISIONS = 1  # the Verifier can send the answer back once
# A specialist gets at most this many model calls per step: without it, a researcher asked
# for something no document contains keeps searching until the whole budget is gone.
MAX_TURNS_PER_STEP = 3


class TeamState(TypedDict, total=False):
    conversation_id: str
    model_id: str
    memory: str
    messages: Annotated[list[dict[str, Any]], operator.add]  # the conversation (input)
    sources: Annotated[list[dict[str, Any]], operator.add]
    pending: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    model_calls: int
    plan: list[dict[str, Any]]  # [{"agent": "researcher", "task": "..."}]
    step: int  # index of the current plan step
    work: Annotated[list[dict[str, Any]], operator.add]  # specialists' messages, append-only
    work_start: int  # where the current step's messages begin in `work`
    notes: Annotated[list[dict[str, Any]], operator.add]  # each step's result
    draft: str
    verdict: dict[str, Any]
    revisions: int
    final: str  # the answer the user gets


def build_team_graph(
    planner: PlannerAgent,
    researcher: AssistantAgent,
    action: AssistantAgent,
    verifier: VerifierAgent,
    research_tools: list[Tool],
    action_tools: list[Tool],
    checkpointer: BaseCheckpointSaver,
    max_model_calls: int,
) -> CompiledStateGraph:
    async def run_agent(agent: Agent, state: TeamState, messages: list[ChatMessage], **extra: Any):
        context = get_runtime(RunContext).context
        agent_state = AgentState(
            conversation_id=state["conversation_id"],
            messages=messages,
            scratch={
                "model_id": state["model_id"],
                "memory": state.get("memory", "(nothing yet)"),
                "model_calls": state.get("model_calls", 0),
                "trace": context.trace,
                **extra,
            },
        )
        result = await agent.run(agent_state, emit)
        if result.get("completion"):
            context.completions.append(result["completion"])
        return result

    def history(state: TeamState) -> list[ChatMessage]:
        return [ChatMessage(**m) for m in state.get("messages", [])]

    async def planner_node(state: TeamState) -> dict[str, Any]:
        result = await run_agent(planner, state, history(state), mode="plan")
        return {"plan": result["plan"], "step": 0, "model_calls": state.get("model_calls", 0) + 1}

    async def dispatch_node(state: TeamState) -> dict[str, Any]:
        """Start the next plan step: announce the handoff, open the specialist's scratchpad."""
        plan, step = state.get("plan", []), state.get("step", 0)
        if step >= len(plan):
            return {}
        task = plan[step]
        await emit(
            AgentStepEvent(
                step_id=f"handoff-{step}", agent="planner", status="completed",
                title=f"Handoff to {task['agent']}", detail=task["task"],
            )
        )  # fmt: skip
        start = ChatMessage(role="user", content=task["task"]).model_dump()
        return {"work": [start], "work_start": len(state.get("work", []))}

    def specialist_node(agent: AssistantAgent):
        async def node(state: TeamState) -> dict[str, Any]:
            work = state.get("work", [])[state.get("work_start", 0) :]
            task = state["plan"][state["step"]]["task"]
            result = await run_agent(
                agent, state, [ChatMessage(**m) for m in work],
                prompt_vars={"task": task, "notes": _notes_text(state)},
            )  # fmt: skip
            return {
                "work": [result["message"].model_dump()],
                "model_calls": state.get("model_calls", 0) + 1,
            }

        return node

    async def finish_step_node(state: TeamState) -> dict[str, Any]:
        """Record what the specialist reported, move on to the next step."""
        task = state["plan"][state["step"]]
        last = state["work"][-1] if state.get("work") else {}
        result = last.get("content") or "(stopped without a result)"
        if last.get("tool_calls"):
            result = "(stopped: step limit reached)"
        note = {"agent": task["agent"], "task": task["task"], "result": result}
        return {"notes": [note], "step": state["step"] + 1}

    async def writer_node(state: TeamState) -> dict[str, Any]:
        issues = state.get("verdict", {})
        result = await run_agent(
            planner, state, history(state), mode="write",
            notes=_notes_text(state), sources=_sources_text(state),
            issues="; ".join(issues.get("unsupported_claims", []) + issues.get("missing", [])),
            revisions=state.get("revisions", 0),
        )  # fmt: skip
        return {"draft": result["draft"], "model_calls": state.get("model_calls", 0) + 1}

    async def verifier_node(state: TeamState) -> dict[str, Any]:
        request = next(
            (m["content"] for m in reversed(state.get("messages", [])) if m["role"] == "user"), ""
        )
        result = await run_agent(
            verifier, state, [], request=request, notes=_notes_text(state),
            sources=_sources_text(state), draft=state["draft"],
            revisions=state.get("revisions", 0),
        )  # fmt: skip
        verdict = result["verdict"]
        done = verdict["approved"] or state.get("revisions", 0) >= MAX_REVISIONS
        final = state["draft"] if done else ""
        return {
            "verdict": verdict,
            "revisions": state.get("revisions", 0) + (0 if final else 1),
            "final": final,
            "model_calls": state.get("model_calls", 0) + 1,
        }

    def after_dispatch(state: TeamState) -> str:
        plan, step = state.get("plan", []), state.get("step", 0)
        return plan[step]["agent"] if step < len(plan) else "writer"

    def after_specialist(tools_node: str):
        def route(state: TeamState) -> str:
            work = state["work"][state.get("work_start", 0) :]
            turns = sum(1 for m in work if m["role"] == "assistant")
            within_budget = (
                state.get("model_calls", 0) < max_model_calls and turns < MAX_TURNS_PER_STEP
            )
            return tools_node if work[-1].get("tool_calls") and within_budget else "finish_step"

        return route

    def after_action_tools(state: TeamState) -> str:
        return "approval" if state.get("pending") else "action"

    def after_verifier(state: TeamState) -> str:
        return END if state.get("final") else "writer"

    graph = StateGraph(TeamState, context_schema=RunContext)
    graph.add_node("planner", planner_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("researcher", specialist_node(researcher))
    graph.add_node("research_tools", make_tools_node(research_tools, key="work"))
    graph.add_node("action", specialist_node(action))
    graph.add_node("action_tools", make_tools_node(action_tools, key="work"))
    graph.add_node("approval", approval_node)
    graph.add_node("act", make_act_node(action_tools, key="work"))
    graph.add_node("finish_step", finish_step_node)
    graph.add_node("writer", writer_node)
    graph.add_node("verifier", verifier_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "dispatch")
    graph.add_conditional_edges("dispatch", after_dispatch, ["researcher", "action", "writer"])
    graph.add_conditional_edges(
        "researcher", after_specialist("research_tools"), ["research_tools", "finish_step"]
    )
    graph.add_edge("research_tools", "researcher")
    graph.add_conditional_edges(
        "action", after_specialist("action_tools"), ["action_tools", "finish_step"]
    )
    graph.add_conditional_edges("action_tools", after_action_tools, ["approval", "action"])
    graph.add_edge("approval", "act")
    graph.add_edge("act", "action")
    graph.add_edge("finish_step", "dispatch")
    graph.add_edge("writer", "verifier")
    graph.add_conditional_edges("verifier", after_verifier, ["writer", END])
    return graph.compile(checkpointer=checkpointer)


def _notes_text(state: TeamState) -> str:
    notes = state.get("notes", [])
    if not notes:
        return "(none yet)"
    return "\n".join(f"- {n['agent']} ({n['task']}): {n['result']}" for n in notes)


def _sources_text(state: TeamState) -> str:
    return format_sources([Chunk(**s) for s in state.get("sources", [])])
