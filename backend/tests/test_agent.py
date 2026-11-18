"""The agent (Phase 4): tool loop, approval pause/resume, safety rules, and the chat route.

A scripted gateway plays the model ("call search_docs", then "call create_ticket", then
"answer"), so these tests check OUR logic: what runs, when, and how often. The rule that
matters most: a write tool never runs without an explicit approval, and never twice.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from agents.assistant import AssistantAgent
from agents.graph import build_graph
from agents.runner import STEP_LIMIT_ANSWER, AgentOutcome, AgentRunner, ApprovalNotFound
from api.deps import get_chat_service, get_prompts, get_settings
from core.agent_config import AgentConfig
from core.db import get_session_factory
from core.events import StreamEvent
from core.interfaces.tool import Tool, ToolResult
from core.llm import ChatMessage, Completion, LLMGateway, ToolCall, ToolTurn
from core.tracing import Tracer
from main import app
from services.chat_service import ChatService
from services.intent import IntentClassification, IntentResult
from tests.conftest import FakeGateway, FakeRetriever, make_chunk
from tests.test_chat import sse_events
from tools.calculator import Calculator
from tools.search_docs import SearchDocs

COMPLETION = Completion(
    model_id="m", litellm_model="fake", input_tokens=100, output_tokens=10, cost_usd=None,
    latency_ms=5, time_to_first_token_ms=None, finish_reason="stop",
)  # fmt: skip


def call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(id=f"call-{name}-{len(arguments)}", name=name, arguments=arguments)


class ScriptedToolGateway(LLMGateway):
    """Returns the scripted ToolTurns in order and records what the model was shown."""

    def __init__(self, turns: list[tuple[str, list[ToolCall]]]):
        self.turns = list(turns)
        self.seen: list[list[ChatMessage]] = []

    async def complete_with_tools(self, model_id, messages, tools, **_: Any) -> ToolTurn:  # type: ignore[override]
        self.seen.append(messages)
        text, calls = self.turns.pop(0)
        return ToolTurn(text=text, tool_calls=calls, completion=COMPLETION)


class TicketInput(BaseModel):
    project: str
    summary: str


class FakeTicketTool(Tool[TicketInput]):
    name = "create_ticket"
    description = "Open a ticket."
    input_model = TicketInput
    requires_approval = True

    def __init__(self) -> None:
        self.created: list[TicketInput] = []

    async def run(self, args: TicketInput) -> ToolResult:
        self.created.append(args)
        return ToolResult(ok=True, output={"key": f"{args.project}-{1000 + len(self.created)}"})


def make_runner(
    gateway: ScriptedToolGateway, tickets: FakeTicketTool, max_calls: int = 6
) -> AgentRunner:
    retriever = FakeRetriever([make_chunk(1, "Laptops are replaced every 3 years.")])
    tools: list[Tool] = [SearchDocs(retriever, top_k=5), Calculator(), tickets]
    assistant = AssistantAgent(gateway, get_prompts(), get_settings(), tools)
    return AgentRunner(build_graph(assistant, tools, InMemorySaver(), max_calls))


async def collect(run: AsyncIterator[StreamEvent | AgentOutcome]) -> tuple[list[Any], AgentOutcome]:
    events, outcome = [], None
    async for item in run:
        if isinstance(item, AgentOutcome):
            outcome = item
        else:
            events.append(item)
    assert outcome is not None
    return events, outcome


def resume(runner: AgentRunner, approval_id: str, decision: str, args: dict | None):
    return runner.resume(
        conversation_id="c1", approval_id=approval_id, decision=decision,  # type: ignore[arg-type]
        args=args, trace=None,
    )  # fmt: skip


def start(runner: AgentRunner, text: str = "help", cid: str = "c1"):
    return runner.start(
        conversation_id=cid, model_id="m", messages=[ChatMessage(role="user", content=text)],
        trace=None,
    )  # fmt: skip


async def test_read_tools_run_and_results_become_citable_sources():
    gateway = ScriptedToolGateway(
        [
            ("", [call("search_docs", query="laptops"), call("calculator", expression="3*12")]),
            ("Laptops last 36 months [1].", []),
        ]
    )
    events, outcome = await collect(start(make_runner(gateway, FakeTicketTool())))

    assert outcome.status == "finished"
    assert outcome.answer == "Laptops last 36 months [1]."
    assert [s.document_id for s in outcome.sources] == ["acme-docs:doc-1.md"]
    tool_events = [(e.tool_name, e.status) for e in events if e.type == "tool_call"]
    assert ("search_docs", "completed") in tool_events
    assert ("calculator", "completed") in tool_events
    tool_results = [m.content for m in gateway.seen[1] if m.role == "tool"]
    assert any(r.startswith("[1] ") for r in tool_results)  # numbered for citing
    assert '{"result": 36}' in tool_results


async def test_write_tool_pauses_and_runs_exactly_once_after_approval():
    tickets = FakeTicketTool()
    gateway = ScriptedToolGateway(
        [("", [call("create_ticket", project="IT", summary="Broken screen")]), ("Done.", [])]
    )
    runner = make_runner(gateway, tickets)
    events, outcome = await collect(start(runner))

    assert outcome.status == "paused" and tickets.created == []  # nothing written yet
    [request] = [e for e in events if e.type == "approval_request"]
    assert request.summary.startswith("create_ticket(") and request.payload["project"] == "IT"

    events, outcome = await collect(resume(runner, request.approval_id, "approve", None))
    assert [t.summary for t in tickets.created] == ["Broken screen"]
    assert outcome.answer == "Done."
    with pytest.raises(ApprovalNotFound):  # answering twice must not create a second ticket
        await runner.check_approval("c1", request.approval_id)
    assert len(tickets.created) == 1


async def test_rejected_actions_are_never_executed():
    tickets = FakeTicketTool()
    gateway = ScriptedToolGateway(
        [("", [call("create_ticket", project="IT", summary="x")]), ("Not done.", [])]
    )
    runner = make_runner(gateway, tickets)
    events, _ = await collect(start(runner))
    [request] = [e for e in events if e.type == "approval_request"]

    events, outcome = await collect(resume(runner, request.approval_id, "reject", None))
    assert tickets.created == [] and outcome.answer == "Not done."
    assert any(e.type == "tool_call" and e.status == "failed" for e in events)
    assert "Rejected by the user" in gateway.seen[-1][-1].content


async def test_invalid_edits_are_not_executed():
    tickets = FakeTicketTool()
    gateway = ScriptedToolGateway(
        [("", [call("create_ticket", project="IT", summary="x")]), ("Not done.", [])]
    )
    runner = make_runner(gateway, tickets)
    events, _ = await collect(start(runner))
    [request] = [e for e in events if e.type == "approval_request"]
    await collect(resume(runner, request.approval_id, "approve", {"project": "IT"}))
    assert tickets.created == []
    assert "edited arguments were invalid" in gateway.seen[-1][-1].content


async def test_edited_arguments_are_validated_and_used():
    tickets = FakeTicketTool()
    gateway = ScriptedToolGateway(
        [("", [call("create_ticket", project="IT", summary="draft")]), ("Ok.", [])]
    )
    runner = make_runner(gateway, tickets)
    events, _ = await collect(start(runner))
    [request] = [e for e in events if e.type == "approval_request"]
    await collect(
        resume(runner, request.approval_id, "approve", {"project": "IT", "summary": "Edited"})
    )
    assert [t.summary for t in tickets.created] == ["Edited"]


async def test_approval_only_works_in_its_own_conversation():
    gateway = ScriptedToolGateway([("", [call("create_ticket", project="IT", summary="s")])])
    runner = make_runner(gateway, FakeTicketTool())
    events, _ = await collect(start(runner, cid="mine"))
    [request] = [e for e in events if e.type == "approval_request"]
    with pytest.raises(ApprovalNotFound):
        await runner.check_approval("someone-else", request.approval_id)
    with pytest.raises(ApprovalNotFound):
        await runner.check_approval("mine", "made-up/approval")


async def test_bad_tool_arguments_go_back_to_the_model_as_errors():
    gateway = ScriptedToolGateway(
        [("", [call("calculator", expression="__import__('os')")]), ("Sorry.", [])]
    )
    events, outcome = await collect(start(make_runner(gateway, FakeTicketTool())))
    assert outcome.answer == "Sorry."
    assert any(e.type == "tool_call" and e.status == "failed" for e in events)
    assert gateway.seen[1][-1].content.startswith("Error: Can't evaluate")


async def test_step_limit_stops_a_looping_model():
    loop = [("", [call("calculator", expression="1+1")])] * 5
    _, outcome = await collect(start(make_runner(ScriptedToolGateway(loop), FakeTicketTool(), 2)))
    assert outcome.answer == STEP_LIMIT_ANSWER


# ---------------------------------------------------------------- through the chat API


class FakeRouter:
    def __init__(self, intent: str, complexity: str = "complex"):
        self.intent = intent
        self.complexity = complexity
        self.calls = 0

    async def classify(self, message: str, model_id=None, *, trace=None) -> IntentResult:
        self.calls += 1
        label = IntentClassification(
            reasoning="scripted", intent=self.intent, complexity=self.complexity, confidence=1.0
        )  # type: ignore[arg-type]
        return IntentResult(classification=label, completion=COMPLETION, prompt_ref="x")


async def test_chat_routes_actions_to_the_agent_and_approval_finishes_the_turn(db: None):
    tickets = FakeTicketTool()
    gateway = ScriptedToolGateway(
        [("", [call("create_ticket", project="IT", summary="Broken")]), ("Opened IT-1001.", [])]
    )
    service = ChatService(
        FakeGateway(), get_prompts(), get_settings(), get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"), FakeRetriever(), top_k=5,
        router=FakeRouter("action_request"), agent=make_runner(gateway, tickets),  # type: ignore[arg-type]
        agent_config=AgentConfig(),
    )  # fmt: skip
    app.dependency_overrides[get_chat_service] = lambda: service
    cid = str(uuid.uuid4())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            message = {"conversation_id": cid, "message": "ticket pls"}
            first = sse_events((await http.post("/api/chat", json=message)).text)
            [request] = [e for e in first if e["type"] == "approval_request"]
            paused_id = first[-1]["message_id"]
            assert (
                first[0]["type"] == "agent_step" and paused_id
            )  # saved, so a reload keeps the card
            stored = (await http.get(f"/api/conversations/{cid}/messages")).json()
            body = {
                "conversation_id": cid,
                "approval_id": request["approval_id"],
                "decision": "approve",
            }
            second = sse_events((await http.post("/api/chat/approval", json=body)).text)
            again = await http.post("/api/chat/approval", json=body)
    finally:
        app.dependency_overrides.clear()

    assert "".join(e["text"] for e in second if e["type"] == "token") == "Opened IT-1001."
    assert second[-1]["type"] == "done" and second[-1]["message_id"] == paused_id  # same message
    assert stored[-1]["error_code"] == "awaiting_approval"
    assert stored[-1]["agent"]["approvals"][0]["state"] == "pending"
    assert again.status_code == 404 and len(tickets.created) == 1


async def test_questions_still_use_the_rag_path(client: AsyncClient, fake_gateway: FakeGateway):
    # The default test client has no router/agent: same behaviour as Phase 3.
    response = await client.post(
        "/api/chat", json={"conversation_id": str(uuid.uuid4()), "message": "How many days?"}
    )
    assert not [e for e in sse_events(response.text) if e["type"] == "agent_step"]
