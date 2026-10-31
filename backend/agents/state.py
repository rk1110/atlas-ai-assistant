"""What the agent graph carries between nodes, and what is saved when it pauses.

Plain dicts and lists only: the checkpointer serialises this state to Postgres, and plain
JSON-like data round-trips safely across versions of our code.
"""

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from core.llm import Completion
from core.tracing import Span


class GraphState(TypedDict):
    conversation_id: str  # checked on resume: an approval only works in its own chat
    model_id: str
    # `Annotated[..., operator.add]` = a reducer: a node returning {"messages": [m]}
    # APPENDS m instead of replacing the list. That is how nodes add to shared history.
    messages: Annotated[list[dict[str, Any]], operator.add]  # ChatMessage dumps, no system
    sources: Annotated[list[dict[str, Any]], operator.add]  # Chunk dumps; [n] = index + 1
    pending: list[dict[str, Any]]  # write calls waiting for approval (ToolCall dumps)
    decisions: list[dict[str, Any]]  # approvals collected, executed by `act`
    model_calls: int


@dataclass
class RunContext:
    """Per-request things the nodes need that must NOT be saved in a checkpoint: the
    Langfuse trace and running token counts. Passed as LangGraph's runtime context."""

    trace: Span | None
    completions: list[Completion] = field(default_factory=list)
