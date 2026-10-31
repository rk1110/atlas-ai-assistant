"""Run or resume the agent graph, and turn what it does into StreamEvents for the chat.

    start()   a new run for one chat turn (a fresh LangGraph "thread")
    resume()  continue a paused run with the human's approval decision

Both yield StreamEvents as they happen (thinking steps, tool calls, approval requests),
then one `AgentOutcome`: finished with an answer, or paused waiting for approval.

A run's thread id goes into each approval id ("<thread>/<tool call id>"), so the approve
request finds the paused run without any extra table. Resuming checks that the run belongs
to the same conversation and is really waiting for that exact approval.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from agents.state import RunContext
from core.events import ApprovalRequestEvent, StreamEvent, stream_event_adapter
from core.interfaces.retriever import Chunk
from core.llm import ChatMessage, Completion
from core.tracing import Span

STEP_LIMIT_ANSWER = (
    "I stopped after several steps without finishing. Could you rephrase or narrow the request?"
)


class AgentOutcome(BaseModel):
    status: Literal["finished", "paused"]
    answer: str  # empty while paused
    sources: list[Chunk]  # every passage the tools returned this turn, [n] = index + 1
    completions: list[Completion]  # one per model call in this segment, for usage totals


class ApprovalNotFound(Exception):
    """No paused run is waiting for this approval in this conversation."""


class AgentRunner:
    def __init__(self, graph: CompiledStateGraph):
        self._graph = graph

    async def start(
        self,
        *,
        conversation_id: str,
        model_id: str,
        messages: list[ChatMessage],
        trace: Span | None,
    ) -> AsyncIterator[StreamEvent | AgentOutcome]:
        initial = {
            "conversation_id": conversation_id,
            "model_id": model_id,
            "messages": [m.model_dump() for m in messages],
            "sources": [],
            "pending": [],
            "decisions": [],
            "model_calls": 0,
        }
        async for item in self._run(str(uuid.uuid4()), initial, trace):
            yield item

    async def check_approval(self, conversation_id: str, approval_id: str) -> None:
        """Raise ApprovalNotFound unless that run is paused on exactly this approval."""
        thread_id, _, call_id = approval_id.partition("/")
        snapshot = await self._graph.aget_state(_config(thread_id))
        values: dict[str, Any] = snapshot.values or {}
        waiting = [i.value.get("approval_id") for i in snapshot.interrupts]
        if values.get("conversation_id") != conversation_id or call_id not in waiting:
            raise ApprovalNotFound(approval_id)

    async def resume(
        self,
        *,
        conversation_id: str,
        approval_id: str,
        decision: Literal["approve", "reject"],
        args: dict[str, Any] | None,
        trace: Span | None,
    ) -> AsyncIterator[StreamEvent | AgentOutcome]:
        await self.check_approval(conversation_id, approval_id)
        thread_id = approval_id.partition("/")[0]
        command = Command(resume={"decision": decision, "args": args})
        async for item in self._run(thread_id, command, trace):
            yield item

    async def _run(
        self, thread_id: str, graph_input: Any, trace: Span | None
    ) -> AsyncIterator[StreamEvent | AgentOutcome]:
        context = RunContext(trace=trace)
        paused = False
        async for mode, chunk in self._graph.astream(
            graph_input,
            _config(thread_id),
            context=context,
            stream_mode=["custom", "updates"],
        ):
            if mode == "custom":  # events the nodes sent with get_stream_writer()
                yield stream_event_adapter.validate_python(chunk)
            elif mode == "updates" and "__interrupt__" in chunk:
                paused = True
                for pause in chunk["__interrupt__"]:
                    request = pause.value
                    yield ApprovalRequestEvent(
                        approval_id=f"{thread_id}/{request['approval_id']}",
                        tool_name=request["tool_name"],
                        summary=request["summary"],
                        payload=request["payload"],
                    )
        values = (await self._graph.aget_state(_config(thread_id))).values
        yield AgentOutcome(
            status="paused" if paused else "finished",
            answer="" if paused else _final_answer(values["messages"]),
            sources=[Chunk(**s) for s in values["sources"]],
            completions=context.completions,
        )


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _final_answer(messages: list[dict[str, Any]]) -> str:
    last = messages[-1] if messages else {}
    if last.get("role") != "assistant" or last.get("tool_calls"):
        return STEP_LIMIT_ANSWER  # stopped by max_model_calls while still calling tools
    return last.get("content") or STEP_LIMIT_ANSWER
