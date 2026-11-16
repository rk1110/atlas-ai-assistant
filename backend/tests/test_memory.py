"""Memory (Phase 4): long-term facts (extract, dedupe, recall, forget) and the running
summary of long conversations. Scripted model + bag-of-words embedder, real Postgres."""

import uuid
from typing import Any

from httpx import AsyncClient

from api.deps import get_chat_service, get_long_term_memory, get_prompts, get_settings
from core.db import get_session_factory
from core.llm import ChatMessage, Completion, LLMGateway
from core.memory_config import LongTermConfig, MemoryConfig, ShortTermConfig
from core.tracing import Tracer
from main import app
from models import Conversation
from services.chat_service import ChatService
from services.memory import (
    NO_MEMORY,
    ConversationSummarizer,
    LongTermMemory,
    MemoryExtraction,
    MemoryItem,
    format_memory,
)
from tests.conftest import TEST_USER, FakeEmbedder, FakeGateway, FakeRetriever
from tests.test_chat import chat

COMPLETION = Completion(
    model_id="m", litellm_model="fake", input_tokens=1, output_tokens=1, cost_usd=None,
    latency_ms=1, time_to_first_token_ms=None, finish_reason="stop",
)  # fmt: skip


class ExtractingGateway(FakeGateway):
    """FakeGateway that also answers memory extraction with scripted facts."""

    def __init__(self, facts: list[str], **kwargs: Any):
        super().__init__(**kwargs)
        self.facts = facts

    async def complete_structured(self, model_id, messages, schema, **_: Any):  # type: ignore[override]
        assert schema is MemoryExtraction
        return MemoryExtraction(facts=self.facts), COMPLETION


def make_memory(gateway: LLMGateway, embedder: FakeEmbedder) -> LongTermMemory:
    return LongTermMemory(
        gateway, get_prompts(), embedder, get_session_factory(), "cheap", LongTermConfig()
    )


async def test_remember_dedupe_recall_and_forget(db: None, fake_embedder: FakeEmbedder):
    gateway = ExtractingGateway(["Works in the Pune office.", "Manager is Priya Nair."])
    memory = make_memory(gateway, fake_embedder)

    stored = await memory.remember("I'm in Pune, my manager is Priya", uuid.uuid4())
    again = await memory.remember("As I said, Pune office", uuid.uuid4())
    assert stored == ["Works in the Pune office.", "Manager is Priya Nair."]
    assert again == []  # same facts again: duplicates are skipped

    recalled = await memory.recall("which office is the user in? pune")
    assert recalled[0].content == "Works in the Pune office."
    assert await memory.forget(recalled[0].id) is True
    assert [m.content for m in await memory.all()] == ["Manager is Priya Nair."]


async def test_most_messages_store_nothing(db: None, fake_embedder: FakeEmbedder):
    memory = make_memory(ExtractingGateway([]), fake_embedder)
    assert await memory.remember("How many vacation days do I get?", uuid.uuid4()) == []
    assert await memory.all() == []


def test_format_memory():
    assert format_memory([], None) == NO_MEMORY
    fact = MemoryItem(id=uuid.uuid4(), content="Works in Pune.")
    text = format_memory([fact], "Asked about leave.")
    assert "- Works in Pune." in text and "Asked about leave." in text


async def test_old_messages_are_folded_into_a_summary(db: None, fake_retriever: FakeRetriever):
    answer_gateway = FakeGateway(chunks=["ok"])
    summary_gateway = FakeGateway(chunks=["User asked about leave and laptops."])
    service = ChatService(
        answer_gateway, get_prompts(), get_settings(), get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"), fake_retriever, top_k=5,
        summarizer=ConversationSummarizer(summary_gateway, get_prompts(), "cheap"),
        memory_config=MemoryConfig(short_term=ShortTermConfig(keep_last_messages=2)),
    )  # fmt: skip
    app.dependency_overrides[get_chat_service] = lambda: service
    try:
        from httpx import ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            cid = str(uuid.uuid4())
            for text in ["first", "second", "third"]:
                await chat(http, cid, text)
    finally:
        app.dependency_overrides.clear()

    # Turn 3 sees 5 messages: 3 are older than the 2-message window -> one summary call.
    assert len(summary_gateway.calls) == 1
    async with get_session_factory()() as session:
        conversation = await session.get(Conversation, uuid.UUID(cid))
        assert conversation is not None
        assert conversation.summary == "User asked about leave and laptops."
        assert conversation.summarized_count == 3
    last_call = answer_gateway.calls[-1]
    assert "User asked about leave and laptops." in last_call[0].content  # in the system prompt
    assert [m.content for m in last_call[1:]] == ["ok", "third"]  # only the recent window


async def test_memories_api(client: AsyncClient, fake_embedder: FakeEmbedder):
    memory = make_memory(ExtractingGateway(["Prefers short answers."]), fake_embedder)
    await memory.remember("keep it short please", uuid.uuid4(), TEST_USER.id)
    app.dependency_overrides[get_long_term_memory] = lambda: memory

    [item] = (await client.get("/api/memories")).json()
    assert item["content"] == "Prefers short answers."
    assert (await client.delete(f"/api/memories/{item['id']}")).status_code == 204
    assert (await client.delete(f"/api/memories/{item['id']}")).status_code == 404


async def test_chat_shows_and_uses_recalled_memories(db: None, fake_embedder: FakeEmbedder):
    memory = make_memory(ExtractingGateway(["Works in the Pune office."]), fake_embedder)
    await memory.remember("I work in Pune", uuid.uuid4(), TEST_USER.id)
    gateway = FakeGateway()
    service = ChatService(
        gateway, get_prompts(), get_settings(), get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"), FakeRetriever(), top_k=5,
        memory=memory,
    )  # fmt: skip
    app.dependency_overrides[get_chat_service] = lambda: service
    try:
        from httpx import ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            events = await chat(http, str(uuid.uuid4()), "Which office parking applies to me?")
    finally:
        app.dependency_overrides.clear()

    step = next(e for e in events if e["type"] == "agent_step")
    assert step["title"] == "Remembered" and "Pune" in step["detail"]
    assert "Works in the Pune office." in gateway.calls[0][0].content
    assert isinstance(gateway.calls[0][0], ChatMessage)
