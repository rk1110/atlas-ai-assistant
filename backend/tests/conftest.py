"""Shared test setup.

- Tests use the `atlas_test` database (TEST_DATABASE_URL), never your real chat history.
- Tracing is switched off, so tests never send traces to Langfuse.
- LLM calls are replaced by `FakeGateway`, embeddings by `FakeEmbedder`, chat retrieval by
  `FakeRetriever`: tests are fast, free and deterministic.

Run on your Mac (Postgres is published on localhost:5432):  cd backend && uv run pytest
"""

import hashlib
import math
import os
import re
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.config import Settings

# --- Point the app at the test database BEFORE any app code reads settings -----------------
_settings = Settings()
if not _settings.test_database_url:
    pytest.exit("TEST_DATABASE_URL is not set in .env", returncode=2)
os.environ["DATABASE_URL"] = _settings.test_database_url
os.environ["LANGFUSE_PUBLIC_KEY"] = ""  # empty = tracing disabled
os.environ["LANGFUSE_SECRET_KEY"] = ""

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.deps import get_chat_service, get_prompts, get_settings  # noqa: E402
from core.db import get_session_factory  # noqa: E402
from core.embeddings import Embedder  # noqa: E402
from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever  # noqa: E402
from core.llm import ChatMessage, Completion, LLMError, LLMGateway, TextDelta  # noqa: E402
from core.tracing import Span, Tracer  # noqa: E402
from main import app  # noqa: E402
from services.chat_service import ChatService  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> None:
    """Bring atlas_test to the latest schema once per test session, exactly like production
    does: by running the Alembic migrations (a subprocess, so Alembic gets its own event loop)."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=os.environ,
        check=True,
    )


@pytest.fixture
async def db() -> None:
    """Empty tables before a test that touches the database."""
    async with get_session_factory()() as session:
        await session.execute(
            text(
                "TRUNCATE conversations, messages, eval_runs, eval_results, documents, chunks,"
                " memories, sim_tickets, sim_slack_messages CASCADE"
            )
        )
        await session.commit()


class FakeGateway(LLMGateway):
    """Stands in for the real gateway: streams scripted text, optionally fails, and records
    what it was sent so tests can assert on the prompt and history."""

    def __init__(self, chunks: list[str] | None = None, error: LLMError | None = None):
        self.chunks = chunks if chunks is not None else ["Hello", " world"]
        self.error = error
        self.calls: list[list[ChatMessage]] = []

    async def stream_chat(  # type: ignore[override]
        self,
        model_id: str,
        messages: list[ChatMessage],
        *,
        trace: Span | None = None,
        name: str = "chat",
        prompt_ref: str | None = None,
    ) -> AsyncIterator[TextDelta | Completion]:
        self.calls.append(messages)
        for chunk in self.chunks:
            yield TextDelta(text=chunk)
        if self.error:
            raise self.error
        yield Completion(
            model_id=model_id,
            litellm_model="fake/model",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.001,
            latency_ms=12,
            time_to_first_token_ms=3,
            finish_reason="stop",
        )


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return FakeGateway()


def make_chunk(number: int, text: str, document_id: str | None = None) -> Chunk:
    return Chunk(
        id=f"chunk-{number}",
        document_id=document_id or f"acme-docs:doc-{number}.md",
        text=text,
        title=f"Doc {number}",
        url=None,
        metadata={"heading": "Policy"},
        score=0.9 - number / 10,
    )


class FakeRetriever(Retriever):
    """Returns scripted chunks and records the queries it was asked."""

    name = "fake"

    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks = chunks if chunks is not None else [
            make_chunk(1, "Employees get 22 vacation days per year."),
            make_chunk(2, "Meals on business trips are covered up to $60 per day."),
        ]  # fmt: skip
        self.queries: list[str] = []

    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        self.queries.append(query)
        return self.chunks[:top_k]


@pytest.fixture
def fake_retriever() -> FakeRetriever:
    return FakeRetriever()


@pytest.fixture
async def client(
    db: None, fake_gateway: FakeGateway, fake_retriever: FakeRetriever
) -> AsyncIterator[AsyncClient]:
    """HTTP client calling the FastAPI app in-process, with the fake LLM and retriever swapped
    in via dependency_overrides (the reason routes receive services through Depends)."""
    service = ChatService(
        fake_gateway,
        get_prompts(),
        get_settings(),
        get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"),
        fake_retriever,
        top_k=5,
    )
    app.dependency_overrides[get_chat_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


class FakeEmbedder(Embedder):
    """Deterministic stand-in for the embedding model: no download, no torch, instant.

    Tokens = words. Vectors = a normalised bag of words (each word hashed into one of 384
    slots), so texts sharing words still get similar vectors and retrieval tests behave
    sensibly, just with "same words" instead of "same meaning".
    """

    dimensions = 384

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()
