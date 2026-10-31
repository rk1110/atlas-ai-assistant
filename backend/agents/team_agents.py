"""The Planner and the Verifier: the two team members that don't use tools (Phase 5).

    PlannerAgent   mode "plan":  request -> steps for the Researcher and the Action agent
                   mode "write": everyone's findings -> the final, cited answer
    VerifierAgent  draft answer -> unsupported claims, missing parts, approved or not

The Researcher and the Action agent are `AssistantAgent`s (agents/assistant.py) with their
own prompts and tools. All four implement the framework-free `Agent` interface.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.config import Settings
from core.events import AgentStepEvent
from core.interfaces.agent import Agent, AgentState, EventEmitter
from core.llm import ChatMessage, LLMGateway, TextDelta
from core.prompts import PromptRegistry

MAX_PLAN_STEPS = 4


class PlanStep(BaseModel):
    agent: Literal["researcher", "action"]
    task: str = Field(description="One concrete instruction for that agent.")


class Plan(BaseModel):
    """Reasoning first: the model explains, then commits to steps (field order matters)."""

    reasoning: str = Field(description="One sentence: what the user wants done.")
    steps: list[PlanStep] = Field(description="1-4 steps, research before action.")


class Verdict(BaseModel):
    reasoning: str = Field(description="One sentence summary of the check.")
    unsupported_claims: list[str] = Field(description="Claims not backed by sources or results.")
    missing: list[str] = Field(description="Parts of the request not addressed or not done.")
    approved: bool = Field(description="true only if both lists are empty.")


class PlannerAgent(Agent):
    name = "planner"
    description = "Splits a request into steps for specialists, then writes the final answer."

    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry, settings: Settings):
        self._gateway = gateway
        self._prompts = prompts
        self._settings = settings

    async def run(self, state: AgentState, emit: EventEmitter) -> dict[str, Any]:
        if state.scratch.get("mode") == "write":
            return await self._write(state, emit)
        return await self._plan(state, emit)

    async def _plan(self, state: AgentState, emit: EventEmitter) -> dict[str, Any]:
        await emit(_step("plan", self.name, "started", "Planning"))
        prompt = self._prompts.render(
            "team_planner",
            assistant_name=self._settings.assistant_name,
            today=date.today().isoformat(),
            memory=state.scratch.get("memory", "(nothing yet)"),
        )
        plan, completion = await self._gateway.complete_structured(
            state.scratch["model_id"],
            [ChatMessage(role="system", content=prompt.text), *state.messages],
            Plan,
            trace=state.scratch.get("trace"),
            name="agent:planner",
            prompt_ref=prompt.ref,
        )
        steps = plan.steps[:MAX_PLAN_STEPS]
        detail = " → ".join(f"{s.agent}: {s.task}" for s in steps) or "Nothing to do; answering"
        await emit(_step("plan", self.name, "completed", "Planning", detail))
        return {"plan": [s.model_dump() for s in steps], "completion": completion}

    async def _write(self, state: AgentState, emit: EventEmitter) -> dict[str, Any]:
        revision = int(state.scratch.get("revisions", 0))
        step_id = f"write-{revision}"
        title = "Writing the answer" if revision == 0 else "Revising the answer"
        await emit(_step(step_id, self.name, "started", title))
        prompt = self._prompts.render(
            "team_writer",
            assistant_name=self._settings.assistant_name,
            notes=state.scratch["notes"],
            sources=state.scratch["sources"],
            issues=state.scratch.get("issues") or "none",
        )
        parts: list[str] = []
        completion = None
        async for chunk in self._gateway.stream_chat(
            state.scratch["model_id"],
            [ChatMessage(role="system", content=prompt.text), *state.messages],
            trace=state.scratch.get("trace"),
            name="agent:writer",
            prompt_ref=prompt.ref,
        ):
            if isinstance(chunk, TextDelta):
                parts.append(chunk.text)
            else:
                completion = chunk
        await emit(_step(step_id, self.name, "completed", title, "Draft ready for the Verifier"))
        return {"draft": "".join(parts).strip(), "completion": completion}


class VerifierAgent(Agent):
    name = "verifier"
    description = "Checks the draft answer against the sources and the request."

    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry):
        self._gateway = gateway
        self._prompts = prompts

    async def run(self, state: AgentState, emit: EventEmitter) -> dict[str, Any]:
        revision = int(state.scratch.get("revisions", 0))
        step_id = f"verify-{revision}"
        await emit(_step(step_id, self.name, "started", "Checking the answer"))
        prompt = self._prompts.render(
            "team_verifier",
            request=state.scratch["request"],
            notes=state.scratch["notes"],
            sources=state.scratch["sources"],
            answer=state.scratch["draft"],
        )
        verdict, completion = await self._gateway.complete_structured(
            state.scratch["model_id"],
            [ChatMessage(role="user", content=prompt.text)],
            Verdict,
            trace=state.scratch.get("trace"),
            name="agent:verifier",
            prompt_ref=prompt.ref,
        )
        problems = verdict.unsupported_claims + verdict.missing
        approved = verdict.approved and not problems
        detail = (
            "Approved: every claim is supported" if approved else "Issues: " + "; ".join(problems)
        )
        await emit(_step(step_id, self.name, "completed", "Checking the answer", detail))
        return {"verdict": {**verdict.model_dump(), "approved": approved}, "completion": completion}


def _step(
    step_id: str, agent: str, status: str, title: str, detail: str | None = None
) -> AgentStepEvent:
    return AgentStepEvent(step_id=step_id, agent=agent, status=status, title=title, detail=detail)  # type: ignore[arg-type]
