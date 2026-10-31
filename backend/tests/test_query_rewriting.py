"""Query rewriting: follow-ups become standalone search queries (Phase 3)."""

import uuid

from httpx import ASGITransport, AsyncClient

from api.deps import get_chat_service, get_prompts, get_settings
from core.db import get_session_factory
from core.llm import ChatMessage, LLMError
from core.tracing import Tracer
from main import app
from services.chat_service import ChatService
from services.query_rewriter import QueryRewriter, clean_query
from tests.conftest import FakeGateway, FakeRetriever
from tests.test_chat import chat

HISTORY = [
    ChatMessage(role="user", content="How many weeks of parental leave does Acme give?"),
    ChatMessage(role="assistant", content="16 weeks, fully paid [1]."),
]


def test_clean_query_strips_labels_quotes_and_extra_lines():
    assert clean_query('"Acme parental leave contact"\nThis resolves "it".') == (
        "Acme parental leave contact"
    )
    assert clean_query("Standalone search query: Acme sick days") == "Acme sick days"
    assert clean_query("  \n ") == ""


async def test_rewrite_sends_the_conversation_and_returns_the_cleaned_query():
    gateway = FakeGateway(chunks=["'Who to contact about ", "Acme parental leave'"])
    rewriter = QueryRewriter(gateway, get_prompts(), "cheap")

    query = await rewriter.rewrite("and who do I ask about it?", HISTORY)

    assert query == "Who to contact about Acme parental leave"
    prompt = gateway.calls[0][0].content
    assert "parental leave" in prompt and "and who do I ask about it?" in prompt


async def test_rewrite_falls_back_to_the_question_on_errors_or_empty_output():
    failing = FakeGateway(chunks=[], error=LLMError("timeout", "slow", "cheap"))
    assert await QueryRewriter(failing, get_prompts(), "m").rewrite("and it?", HISTORY) == "and it?"
    empty = FakeGateway(chunks=["  "])
    assert await QueryRewriter(empty, get_prompts(), "m").rewrite("and it?", HISTORY) == "and it?"


async def test_chat_rewrites_follow_ups_only_and_reports_what_it_searched(db: None):
    answer_gateway = FakeGateway()
    rewrite_gateway = FakeGateway(chunks=["Acme parental leave contact"])
    retriever = FakeRetriever()
    service = ChatService(
        answer_gateway,
        get_prompts(),
        get_settings(),
        get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"),
        retriever,
        top_k=5,
        query_rewriter=QueryRewriter(rewrite_gateway, get_prompts(), "cheap"),
    )
    app.dependency_overrides[get_chat_service] = lambda: service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            cid = str(uuid.uuid4())
            first = await chat(http, cid, "How many weeks of parental leave does Acme give?")
            second = await chat(http, cid, "and who do I ask about it?")
    finally:
        app.dependency_overrides.clear()

    assert len(rewrite_gateway.calls) == 1  # the first question needed no rewrite
    assert not [e for e in first if e["type"] == "agent_step"]
    step = next(e for e in second if e["type"] == "agent_step")
    assert step["title"] == "Searched for" and step["detail"] == "Acme parental leave contact"
    assert retriever.queries == [
        "How many weeks of parental leave does Acme give?",
        "Acme parental leave contact",
    ]
    # The answering model still sees the user's own words, not the rewrite.
    assert answer_gateway.calls[1][-1].content == "and who do I ask about it?"
