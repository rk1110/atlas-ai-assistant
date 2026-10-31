"""The agent team (Phase 5): plan -> specialists -> write -> verify, with approval in between.

A scripted gateway plays every agent: structured calls return the next Plan / Verdict,
tool-calling calls return the next specialist turn, streamed calls return the draft.
"""

from collections.abc import AsyncIterator
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from agents.assistant import AssistantAgent
from agents.runner import STEP_LIMIT_ANSWER, AgentOutcome, AgentRunner
from agents.team import build_team_graph
from agents.team_agents import Plan, PlannerAgent, PlanStep, Verdict, VerifierAgent
from api.deps import get_prompts, get_settings
from core.interfaces.tool import Tool
from core.llm import ChatMessage, Completion, LLMGateway, TextDelta, ToolCall, ToolTurn
from tests.conftest import FakeRetriever, make_chunk
from tests.test_agent import FakeTicketTool, call, collect, resume
from tools.search_docs import SearchDocs

COMPLETION = Completion(
    model_id="m", litellm_model="fake", input_tokens=10, output_tokens=5, cost_usd=None,
    latency_ms=5, time_to_first_token_ms=None, finish_reason="stop",
)  # fmt: skip

APPROVED = Verdict(reasoning="fine", unsupported_claims=[], missing=[], approved=True)


class TeamGateway(LLMGateway):
    def __init__(
        self,
        plan: Plan,
        turns: list[tuple[str, list[ToolCall]]],
        drafts: list[str],
        verdicts: list[Verdict],
    ):
        self.plan, self.turns = plan, list(turns)
        self.drafts, self.verdicts = list(drafts), list(verdicts)
        self.tool_prompts: list[str] = []
        self.writer_prompts: list[str] = []

    async def complete_structured(self, model_id, messages, schema, **_: Any):  # type: ignore[override]
        if schema is Plan:
            return self.plan, COMPLETION
        assert schema is Verdict
        return self.verdicts.pop(0), COMPLETION

    async def complete_with_tools(self, model_id, messages, tools, **_: Any) -> ToolTurn:  # type: ignore[override]
        self.tool_prompts.append(messages[0].content)
        text, calls = self.turns.pop(0)
        return ToolTurn(text=text, tool_calls=calls, completion=COMPLETION)

    async def stream_chat(self, model_id, messages, **_: Any) -> AsyncIterator[Any]:  # type: ignore[override]
        self.writer_prompts.append(messages[0].content)
        yield TextDelta(text=self.drafts.pop(0))
        yield COMPLETION


def make_team(gateway: TeamGateway, tickets: FakeTicketTool) -> AgentRunner:
    search = SearchDocs(FakeRetriever([make_chunk(1, "Report stolen laptops to Security.")]), 5)
    research_tools: list[Tool] = [search]
    action_tools: list[Tool] = [tickets]
    prompts, settings = get_prompts(), get_settings()
    graph = build_team_graph(
        PlannerAgent(gateway, prompts, settings),
        AssistantAgent(gateway, prompts, settings, research_tools, name="researcher",
                       prompt_name="team_researcher", title="Researching"),
        AssistantAgent(gateway, prompts, settings, action_tools, name="action",
                       prompt_name="team_action", title="Acting"),
        VerifierAgent(gateway, prompts),
        research_tools, action_tools, InMemorySaver(), max_model_calls=14,
    )  # fmt: skip
    return AgentRunner(graph)


def start(runner: AgentRunner):
    return runner.start(
        conversation_id="c1", model_id="m",
        messages=[ChatMessage(role="user", content="Laptop stolen: check policy, open a ticket")],
        trace=None,
    )  # fmt: skip


PLAN = Plan(
    reasoning="Policy, then ticket.",
    steps=[
        PlanStep(agent="researcher", task="Find the stolen laptop policy"),
        PlanStep(agent="action", task="Open a SEC ticket"),
    ],
)


async def test_team_plans_hands_off_pauses_for_approval_and_verifies():
    tickets = FakeTicketTool()
    gateway = TeamGateway(
        PLAN,
        turns=[
            ("", [call("search_docs", query="stolen laptop")]),  # researcher: search
            ("Report to Security within 1 hour [1].", []),  # researcher: findings
            ("", [call("create_ticket", project="SEC", summary="Stolen laptop")]),  # action
            ("Opened SEC-1001.", []),  # action: report back
        ],
        drafts=["Reported per policy [1]; ticket SEC-1001 is open."],
        verdicts=[APPROVED],
    )
    runner = make_team(gateway, tickets)
    events, outcome = await collect(start(runner))

    assert outcome.status == "paused" and tickets.created == []
    agents = [e.agent for e in events if e.type == "agent_step" and e.status == "started"]
    assert agents[:3] == ["planner", "researcher", "researcher"]  # plan, search, findings
    handoffs = [e.title for e in events if e.type == "agent_step" and e.title.startswith("Handoff")]
    assert handoffs == ["Handoff to researcher", "Handoff to action"]
    [request] = [e for e in events if e.type == "approval_request"]

    events, outcome = await collect(resume(runner, request.approval_id, "approve", None))
    assert len(tickets.created) == 1
    assert outcome.answer == "Reported per policy [1]; ticket SEC-1001 is open."
    assert [s.document_id for s in outcome.sources] == ["acme-docs:doc-1.md"]
    verifier = [e for e in events if e.type == "agent_step" and e.agent == "verifier"]
    assert verifier[-1].detail.startswith("Approved")
    # The writer saw every specialist's result, and the specialists only their own task.
    assert "Report to Security within 1 hour [1]." in gateway.writer_prompts[0]
    assert "Opened SEC-1001." in gateway.writer_prompts[0]
    assert "Open a SEC ticket" in gateway.tool_prompts[2]


async def test_verifier_sends_the_answer_back_once_with_its_issues():
    rejecting = Verdict(reasoning="x", unsupported_claims=["SEC-9999 isn't real"], missing=[],
                        approved=False)  # fmt: skip
    gateway = TeamGateway(
        Plan(reasoning="answer", steps=[PlanStep(agent="researcher", task="Find the policy")]),
        turns=[("Report within 1 hour.", [])],
        drafts=["Ticket SEC-9999 opened.", "Report within 1 hour."],
        verdicts=[rejecting, rejecting],
    )
    _, outcome = await collect(start(make_team(gateway, FakeTicketTool())))
    assert outcome.answer == "Report within 1 hour."  # the revision; no third attempt
    assert "SEC-9999 isn't real" in gateway.writer_prompts[1]
    assert gateway.verdicts == []


async def test_an_empty_plan_goes_straight_to_the_answer():
    gateway = TeamGateway(
        Plan(reasoning="nothing to do", steps=[]), turns=[], drafts=["Hello!"], verdicts=[APPROVED]
    )
    _, outcome = await collect(start(make_team(gateway, FakeTicketTool())))
    assert outcome.answer == "Hello!"


def test_runner_final_answer_for_team_state():
    from agents.runner import _final_answer

    assert _final_answer({"plan": [], "final": "", "messages": []}) == STEP_LIMIT_ANSWER
    assert _final_answer({"plan": [], "final": "ok", "messages": []}) == "ok"
    assert isinstance(AgentOutcome, type)
