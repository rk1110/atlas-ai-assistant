"""Shared test setup.

- Tests use the `atlas_test` database (TEST_DATABASE_URL), never your real chat history.
- Tracing is switched off, so tests never send traces to Langfuse.
- LLM calls are replaced by `FakeGateway`: tests are fast, free and deterministic.

Run on your Mac (Postgres is published on localhost:5432):  cd backend && uv run pytest
"""

import os
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
            text("TRUNCATE conversations, messages, eval_runs, eval_results CASCADE")
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


@pytest.fixture
async def client(db: None, fake_gateway: FakeGateway) -> AsyncIterator[AsyncClient]:
    """HTTP client calling the FastAPI app in-process, with the fake LLM swapped in via
    dependency_overrides (the reason routes receive services through Depends)."""
    service = ChatService(
        fake_gateway,
        get_prompts(),
        get_settings(),
        get_session_factory(),
        Tracer(None, "http://langfuse.test", "atlas"),
    )
    app.dependency_overrides[get_chat_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
