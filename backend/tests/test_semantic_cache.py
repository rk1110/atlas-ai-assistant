"""The semantic cache (Phase 7B): a repeated question is answered without a model call, and
an answer is never reused across a boundary that shaped it (access, facts, documents)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from api.deps import get_chat_service, get_prompts
from core.access import set_reader_tags
from core.cache_config import CacheConfig
from core.config import get_settings
from core.db import get_session_factory
from core.events import CitationEvent
from core.tracing import Tracer
from main import app
from models import DocumentRecord
from services.chat_service import ChatService
from services.semantic_cache import SemanticCache
from tests.conftest import FakeEmbedder, FakeGateway, FakeRetriever
from tests.test_chat import chat

QUESTION = "How many vacation days do employees get?"


def cache(threshold: float = 0.9) -> SemanticCache:
    config = CacheConfig(similarity_threshold=threshold)
    return SemanticCache(FakeEmbedder(), get_session_factory(), config)


async def scope(c: SemanticCache, question: str = QUESTION, facts: list[str] | None = None):
    return await c.scope(question, model_id="m", prompt_ref="chat_system@v6", facts=facts or [])


async def stored(c: SemanticCache, question: str = QUESTION, **kwargs) -> None:
    citation = CitationEvent(citation_id="1", document_id="d", title="Leave", snippet="22 days")
    await c.store(
        await scope(c, question, **kwargs), question, "22 days [1]", [citation], "m", 0.01
    )


@pytest.fixture
async def gateway_client(db, fake_retriever: FakeRetriever) -> AsyncIterator:
    gateway = FakeGateway(chunks=["Employees get 22 days [1]."])
    service = ChatService(
        gateway, get_prompts(), get_settings(), get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"), fake_retriever, top_k=5,
        cache=SemanticCache(FakeEmbedder(), get_session_factory(), CacheConfig()),
    )  # fmt: skip
    app.dependency_overrides[get_chat_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield gateway, http
    app.dependency_overrides.clear()


async def test_a_repeated_question_is_answered_without_a_model_call(gateway_client):
    gateway, http = gateway_client
    await chat(http, str(uuid.uuid4()), QUESTION)
    events = await chat(http, str(uuid.uuid4()), "how many vacation days do employees get")

    assert len(gateway.calls) == 1  # the second answer came from the cache
    step = next(e for e in events if e["type"] == "agent_step")
    assert step["agent"] == "cache" and "No model call" in step["detail"]
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert text == "Employees get 22 days [1]."
    assert [e["document_id"] for e in events if e["type"] == "citation"] == ["acme-docs:doc-1.md"]
    assert events[-1]["type"] == "done"


async def test_retry_always_asks_the_model_again(gateway_client):
    gateway, http = gateway_client
    cid = str(uuid.uuid4())
    await chat(http, cid, QUESTION)
    await chat(http, cid, QUESTION, retry=True)
    assert len(gateway.calls) == 2


async def test_a_question_that_only_looks_similar_misses(db):
    c = cache()
    await stored(c)
    other = "How many vacation days do employees get after five years of service?"
    assert await c.lookup(await scope(c, other)) is None


async def test_other_access_never_sees_the_answer(db):
    c = cache()
    set_reader_tags(["public", "hr"])
    await stored(c)  # written by someone with HR access
    set_reader_tags(["public"])
    assert await c.lookup(await scope(c)) is None
    set_reader_tags(["public", "hr"])
    assert await c.lookup(await scope(c)) is not None


async def test_different_personal_facts_never_share_an_answer(db):
    c = cache()
    await stored(c, facts=["Has a 14-inch MacBook Pro."])
    assert await c.lookup(await scope(c, facts=[])) is None
    assert await c.lookup(await scope(c, facts=["Has a 14-inch MacBook Pro."])) is not None


async def test_changed_documents_start_a_fresh_cache(db):
    c = cache()
    async with get_session_factory()() as session:
        session.add(DocumentRecord(
            id="acme-docs:leave.md", source="acme-docs", title="Leave",
            content_type="markdown", content_hash="x",
        ))  # fmt: skip
        await session.commit()
    await stored(c)
    assert await c.lookup(await scope(c)) is not None
    async with get_session_factory()() as session:
        await session.execute(update(DocumentRecord).values(title="Leave (updated)"))
        await session.commit()
    assert await c.lookup(await scope(c)) is None
