"""`Agent`: one step-taking unit in an agent graph. Implemented in Phase 4 (one agent) and
Phase 5 (Planner, Researcher, Action, Verifier).

An agent is a loop around the LLM: look at the state, decide (answer, or call a tool), act,
repeat. In LangGraph, a workflow is a *graph*: nodes are functions that take the shared state
and return updates to it; edges decide which node runs next. Each Atlas agent is one node.

This interface deliberately does not import LangGraph: agents depend on our own types, and a
thin adapter in `agents/` registers each one as a graph node. If we ever swap orchestration
frameworks, agents don't change.

Agents report progress through `emit`, which pushes `StreamEvent`s (agent_step, tool_call,
approval_request, token) onto the same SSE stream the chat uses. That is what makes every
agent step visible live in the UI.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from core.events import StreamEvent
from core.llm import ChatMessage

# A function an agent calls to send an event to the UI, e.g. `await emit(AgentStepEvent(...))`.
EventEmitter = Callable[[StreamEvent], Awaitable[None]]


class AgentState(BaseModel):
    """The shared state passed between agents in a graph. Phase 4-5 add fields (plan,
    retrieved chunks, pending approvals); every agent reads what it needs and returns updates."""

    conversation_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    scratch: dict[str, Any] = Field(default_factory=dict)  # untyped notes until fields settle


class Agent(ABC):
    name: ClassVar[str]  # "planner", "researcher", ...; shown in the agent panel
    description: ClassVar[str]  # what it's for; a supervisor agent uses this to route work

    @abstractmethod
    async def run(self, state: AgentState, emit: EventEmitter) -> dict[str, Any]:
        """Do one turn of work and return a partial state update, e.g. {"messages": [...]}.

        Returning *updates* (not a whole new state) is the LangGraph node convention: the
        graph merges them, so agents running in sequence don't overwrite each other's fields.
        """
