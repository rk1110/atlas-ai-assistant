"""The assistant: the model step of the agent loop.

Each turn it sees the system prompt, the conversation so far (including every tool result)
and the tool definitions, and returns either a final answer or tool calls. It implements
the framework-free `Agent` interface; graph.py adapts it into a LangGraph node.
"""

from datetime import date
from typing import Any

from core.config import Settings
from core.events import AgentStepEvent
from core.interfaces.agent import Agent, AgentState, EventEmitter
from core.interfaces.tool import Tool
from core.llm import ChatMessage, LLMGateway
from core.prompts import PromptRegistry
from core.tracing import Span


class AssistantAgent(Agent):
    name = "assistant"
    description = "Answers from the knowledge base and takes actions with tools."

    def __init__(
        self, gateway: LLMGateway, prompts: PromptRegistry, settings: Settings, tools: list[Tool]
    ):
        self._gateway = gateway
        self._prompts = prompts
        self._settings = settings
        self._definitions = [t.definition() for t in tools]

    async def run(self, state: AgentState, emit: EventEmitter) -> dict[str, Any]:
        step = int(state.scratch.get("model_calls", 0)) + 1
        step_id = f"think-{step}"
        await emit(
            AgentStepEvent(
                step_id=step_id, agent=self.name, status="started", title="Thinking", detail=None
            )
        )
        prompt = self._prompts.render(
            "agent_system",
            assistant_name=self._settings.assistant_name,
            today=date.today().isoformat(),
            memory=state.scratch.get("memory", "(nothing yet)"),
        )
        trace: Span | None = state.scratch.get("trace")
        turn = await self._gateway.complete_with_tools(
            state.scratch["model_id"],
            [ChatMessage(role="system", content=prompt.text), *state.messages],
            self._definitions,
            trace=trace,
            name=f"agent:{self.name}",
            prompt_ref=prompt.ref,
        )
        detail = (
            "Decided to use " + ", ".join(sorted({c.name for c in turn.tool_calls}))
            if turn.tool_calls
            else "Writing the answer"
        )
        await emit(
            AgentStepEvent(
                step_id=step_id,
                agent=self.name,
                status="completed",
                title="Thinking",
                detail=detail,
            )
        )
        message = ChatMessage(
            role="assistant", content=turn.text, tool_calls=turn.tool_calls or None
        )
        return {"message": message, "completion": turn.completion}
