"""A tool-using agent: the model step of an agent loop.

Each turn it sees its system prompt, the conversation so far (including every tool result)
and its tool definitions, and returns either a final text or tool calls. It implements the
framework-free `Agent` interface; graph.py / team.py adapt it into LangGraph nodes.

The single agent (Phase 4) is one of these with every tool. In the team (Phase 5) the
Researcher and the Action agent are two of these, each with its own prompt and only its
own tools: a narrow toolset makes each specialist's choices easier and safer.
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
        self,
        gateway: LLMGateway,
        prompts: PromptRegistry,
        settings: Settings,
        tools: list[Tool],
        *,
        name: str = "assistant",
        prompt_name: str = "agent_system",
        title: str = "Thinking",
    ):
        self._gateway = gateway
        self._prompts = prompts
        self._settings = settings
        self._definitions = [t.definition() for t in tools]
        self.name = name  # type: ignore[misc]  # "assistant", "researcher", "action"
        self._prompt_name = prompt_name
        self._title = title

    async def run(self, state: AgentState, emit: EventEmitter) -> dict[str, Any]:
        step = int(state.scratch.get("model_calls", 0)) + 1
        step_id = f"{self.name}-{step}"
        await emit(
            AgentStepEvent(
                step_id=step_id, agent=self.name, status="started", title=self._title, detail=None
            )
        )
        prompt = self._prompts.render(
            self._prompt_name,
            assistant_name=self._settings.assistant_name,
            today=date.today().isoformat(),
            memory=state.scratch.get("memory", "(nothing yet)"),
            **state.scratch.get("prompt_vars", {}),  # e.g. the team's task and notes
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
            else ("Writing the answer" if self.name == "assistant" else "Reporting back")
        )
        await emit(
            AgentStepEvent(
                step_id=step_id,
                agent=self.name,
                status="completed",
                title=self._title,
                detail=detail,
            )
        )
        message = ChatMessage(
            role="assistant", content=turn.text, tool_calls=turn.tool_calls or None
        )
        return {"message": message, "completion": turn.completion}
