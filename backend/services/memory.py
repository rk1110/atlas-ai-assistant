"""Memory (Phase 4): what Atlas carries between messages and between conversations.

    short-term  ConversationSummarizer   the newest messages go to the model word for word;
                                         older ones are folded into a running summary
    long-term   LongTermMemory           lasting facts about the user, extracted after each
                                         turn, stored with embeddings, recalled by similarity

Why both: the model API is stateless, so "memory" is whatever we put back into the prompt.
Sending every old message costs tokens on every turn and eventually overflows the context
window; a summary keeps the gist at a fixed size. And a new conversation starts empty, so
facts the user told Atlas last week ("I'm in the Pune office") must be stored separately
and looked up, exactly like documents: embed, then find the nearest.
"""

import logging
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.embeddings import Embedder
from core.llm import ChatMessage, LLMError, LLMGateway, TextDelta
from core.memory_config import LongTermConfig
from core.prompts import PromptRegistry
from core.tracing import Span
from models import MemoryRecord

logger = logging.getLogger(__name__)

MAX_FACTS_PER_MESSAGE = 3
NO_MEMORY = "(nothing yet)"


class MemoryItem(BaseModel):
    id: uuid.UUID
    content: str
    score: float | None = None  # similarity to the current question, when recalled


class MemoryExtraction(BaseModel):
    facts: list[str] = Field(
        description="Lasting facts about the user, third person; usually an empty list."
    )


class LongTermMemory:
    def __init__(
        self,
        gateway: LLMGateway,
        prompts: PromptRegistry,
        embedder: Embedder,
        session_factory: async_sessionmaker[AsyncSession],
        model_id: str,
        config: LongTermConfig,
    ):
        self._gateway = gateway
        self._prompts = prompts
        self._embedder = embedder
        self._session_factory = session_factory
        self._model_id = model_id
        self._config = config

    async def recall(self, query: str, user_id: uuid.UUID | None = None) -> list[MemoryItem]:
        """The user's stored facts most similar to the question (all, while there are few)."""
        vector = await self._embedder.embed_query(query)
        distance = MemoryRecord.embedding.cosine_distance(vector)
        async with self._session_factory() as session:
            rows = await session.execute(
                select(MemoryRecord, distance)
                .where(_owned_by(user_id))
                .order_by(distance)
                .limit(self._config.recall_top_k)
            )
            return [
                MemoryItem(id=m.id, content=m.content, score=round(1 - float(d), 4))
                for m, d in rows.all()
            ]

    async def remember(
        self, message: str, conversation_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> list[str]:
        """Extract facts from a user message and store the new ones. Runs after the answer
        (in the background), so it never slows a reply down. Returns what was stored."""
        prompt = self._prompts.render("memory_extract", message=message)
        try:
            extraction, _ = await self._gateway.complete_structured(
                self._model_id,
                [ChatMessage(role="user", content=prompt.text)],
                MemoryExtraction,
                name="memory_extract",
                prompt_ref=prompt.ref,
            )
        except LLMError as err:
            logger.warning("memory extraction failed [%s]", err.kind)
            return []
        facts = [f.strip() for f in extraction.facts if f.strip()][:MAX_FACTS_PER_MESSAGE]
        if not facts:
            return []
        vectors = await self._embedder.embed_documents(facts)
        stored = []
        async with self._session_factory() as session:
            for fact, vector in zip(facts, vectors, strict=True):
                if await self._has_near_duplicate(session, vector, user_id):
                    continue
                session.add(
                    MemoryRecord(
                        content=fact,
                        embedding=vector,
                        source_conversation_id=conversation_id,
                        user_id=user_id,
                    )
                )
                stored.append(fact)
            await session.commit()
        if stored:
            logger.info("remembered %d new fact(s)", len(stored))
        return stored

    async def all(self, user_id: uuid.UUID | None = None) -> list[MemoryItem]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MemoryRecord)
                .where(_owned_by(user_id))
                .order_by(MemoryRecord.created_at.desc())
            )
            return [MemoryItem(id=m.id, content=m.content) for m in rows.all()]

    async def forget(self, memory_id: uuid.UUID, user_id: uuid.UUID | None = None) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(MemoryRecord).where(MemoryRecord.id == memory_id, _owned_by(user_id))
            )
            await session.commit()
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def _has_near_duplicate(
        self, session: AsyncSession, vector: list[float], user_id: uuid.UUID | None
    ) -> bool:
        distance = MemoryRecord.embedding.cosine_distance(vector)
        closest = await session.scalar(
            select(distance).where(_owned_by(user_id)).order_by(distance).limit(1)
        )
        return closest is not None and 1 - float(closest) >= self._config.duplicate_similarity


def _owned_by(user_id: uuid.UUID | None) -> ColumnElement[bool]:
    """Phase 7: each user sees only their own facts. None = no login (tests, scripts)."""
    if user_id is None:
        return MemoryRecord.user_id.is_(None)
    return MemoryRecord.user_id == user_id


class ConversationSummarizer:
    """Folds messages that fall out of the recent window into a running summary."""

    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry, model_id: str):
        self._gateway = gateway
        self._prompts = prompts
        self._model_id = model_id

    async def fold(
        self, previous: str | None, messages: list[ChatMessage], trace: Span | None = None
    ) -> str | None:
        """New summary = previous summary + these messages. None if the model call fails
        (the caller then keeps the old summary: losing detail beats failing the turn)."""
        prompt = self._prompts.render(
            "conversation_summary",
            previous_summary=previous or "(none yet)",
            messages="\n".join(f"{m.role}: {' '.join(m.content.split())[:800]}" for m in messages),
        )
        parts: list[str] = []
        try:
            async for chunk in self._gateway.stream_chat(
                self._model_id,
                [ChatMessage(role="user", content=prompt.text)],
                trace=trace,
                name="summarize_history",
                prompt_ref=prompt.ref,
            ):
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
        except LLMError as err:
            logger.warning("summarizing history failed [%s]", err.kind)
            return None
        return "".join(parts).strip() or None


def format_memory(facts: list[MemoryItem], summary: str | None) -> str:
    """The $memory block of the prompts: user facts, then the older conversation."""
    lines = []
    if facts:
        lines.append("About the user:")
        lines += [f"- {f.content}" for f in facts]
    if summary:
        lines.append("Earlier in this conversation (summary):")
        lines.append(summary)
    return "\n".join(lines) if lines else NO_MEMORY
