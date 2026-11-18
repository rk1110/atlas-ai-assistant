"""Model routing (Phase 7B): in "Auto", the classifier's complexity label picks the answer
model. Simple -> cheap model; complex, unlabelled or agent -> strong model."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import get_catalog, get_chat_service, get_prompts
from core.config import Settings, get_settings
from core.db import get_session_factory
from core.llm import ChatMessage, LLMError
from core.model_catalog import (
    AUTO_MODEL_ID,
    CatalogDefaults,
    ModelCatalog,
    ModelEntry,
    RoutingConfig,
)
from core.tracing import Span, Tracer
from main import app
from services.chat_service import ChatService
from tests.conftest import FakeGateway, FakeRetriever
from tests.test_agent import FakeRouter
from tests.test_chat import chat


class RecordingGateway(FakeGateway):
    """Remembers which model answered."""

    def __init__(self) -> None:
        super().__init__(chunks=["ok"])
        self.models: list[str] = []

    async def stream_chat(self, model_id: str, messages: list[ChatMessage], **kwargs):  # type: ignore[override]
        self.models.append(model_id)
        async for chunk in super().stream_chat(model_id, messages, **kwargs):
            yield chunk


class BrokenRouter:
    async def classify(self, message: str, model_id=None, *, trace: Span | None = None):
        raise LLMError("timeout", "slow", "cheap")


def catalog(enabled: bool = True) -> ModelCatalog:
    entries = [
        ModelEntry(id=i, label=i.title(), provider="test", litellm_model=f"fake/{i}")
        for i in ("cheap", "strong")
    ]
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://x@y/z")  # type: ignore[call-arg]
    routing = RoutingConfig(enabled=enabled, simple="cheap", complex="strong")
    return ModelCatalog(
        entries, CatalogDefaults(chat="strong", cheap="cheap"), settings, None, routing
    )


@pytest.fixture
def routed(db, fake_retriever: FakeRetriever):
    async def make(router) -> AsyncIterator:
        gateway = RecordingGateway()
        service = ChatService(
            gateway, get_prompts(), get_settings(), get_session_factory(),
            Tracer(None, "http://langfuse.test", "atlas"), fake_retriever, top_k=5,
            router=router, catalog=catalog(),
        )  # fmt: skip
        app.dependency_overrides[get_chat_service] = lambda: service
        app.dependency_overrides[get_catalog] = catalog
        http = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        return gateway, http

    yield make
    app.dependency_overrides.clear()


async def ask_auto(http: AsyncClient) -> list[dict]:
    return await chat(http, str(uuid.uuid4()), "What does DRI mean?", model_id=AUTO_MODEL_ID)


async def test_simple_questions_go_to_the_cheap_model(routed):
    gateway, http = await routed(FakeRouter("question", complexity="simple"))
    events = await ask_auto(http)
    assert gateway.models == ["cheap"]
    step = next(e for e in events if e.get("step_id") == "model_route")
    assert step["title"] == "Auto picked Cheap" and step["detail"].startswith("Simple question")


async def test_complex_questions_go_to_the_strong_model(routed):
    gateway, http = await routed(FakeRouter("question", complexity="complex"))
    await ask_auto(http)
    assert gateway.models == ["strong"]


async def test_a_failed_classification_falls_back_to_the_strong_model(routed):
    gateway, http = await routed(BrokenRouter())
    events = await ask_auto(http)
    assert gateway.models == ["strong"]
    assert (
        "Couldn't judge" in next(e for e in events if e.get("step_id") == "model_route")["detail"]
    )


async def test_a_named_model_is_never_rerouted(routed):
    router = FakeRouter("question", complexity="simple")
    gateway, http = await routed(router)
    await chat(http, str(uuid.uuid4()), "What does DRI mean?", model_id="strong")
    assert gateway.models == ["strong"]
    assert router.calls == 0  # no agent and no Auto: nothing needs the label


def test_agent_turns_always_use_the_strong_model():
    service = ChatService.__new__(ChatService)
    service._catalog = catalog()
    model, step = service._auto_model(None, agent=True)
    assert model == "strong" and "Actions" in step.detail


def test_auto_is_only_selectable_when_routing_is_on():
    assert catalog().is_selectable(AUTO_MODEL_ID) and catalog().default_selection == AUTO_MODEL_ID
    off = catalog(enabled=False)
    assert not off.is_selectable(AUTO_MODEL_ID) and off.default_selection == "strong"


async def test_model_list_offers_auto_first(client: AsyncClient):
    app.dependency_overrides[get_catalog] = catalog
    body = (await client.get("/api/models")).json()
    assert body["models"][0]["id"] == AUTO_MODEL_ID and body["default_model"] == AUTO_MODEL_ID
