"""Semantic cache (Phase 7B): reuse an answer when a new question means the same thing.

An exact-match cache misses almost everything, because people rarely type the same words
twice. A semantic cache compares meaning instead: it embeds the (rewritten, standalone)
question with the same local model that embeds documents, and looks for a saved question whose
vector is close enough (cosine similarity >= `similarity_threshold`). On a hit, the saved
answer and citations are returned with no model call: free and near-instant.

The danger is serving an answer to a question that only LOOKS similar ("vacation days for new
employees" vs "... after five years"). That's what the threshold is for, and it is measured on
near-miss pairs by `python -m evals.cache_run`, not guessed.

Who may reuse an answer is decided by `scope_key` (see models/cache.py): access tags, model,
prompt version, the user's recalled facts and the knowledge-base state must all match.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.access import reader_tags
from core.cache_config import CacheConfig
from core.embeddings import Embedder
from core.events import CitationEvent
from models import DocumentRecord, SemanticCacheEntry

logger = logging.getLogger(__name__)


@dataclass
class CacheHit:
    question: str  # the saved question that matched
    answer: str
    citations: list[CitationEvent]
    similarity: float
    saved_usd: float | None  # what answering again would have cost
    created_at: datetime


@dataclass
class CacheScope:
    """Everything besides the question that shaped an answer. Built once per turn."""

    key: str
    vector: list[float]  # the question's embedding, reused by lookup and store


class SemanticCache:
    def __init__(
        self,
        embedder: Embedder,
        session_factory: async_sessionmaker[AsyncSession],
        config: CacheConfig,
    ):
        self._embedder = embedder
        self._session_factory = session_factory
        self._config = config

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    async def scope(
        self, question: str, *, model_id: str, prompt_ref: str, facts: list[str]
    ) -> CacheScope:
        """Facts are part of the key, not a reason to skip: recall returns the user's top
        facts for EVERY question, so "skip when memory is used" would never hit for anyone
        with memories. With facts in the key, an answer is only reused by someone whose
        prompt carried exactly the same facts, so it can't reveal anything new about anyone.
        """
        tags = reader_tags()
        parts = {
            "access": sorted(tags) if tags is not None else "all",
            "model": model_id,
            "prompt": prompt_ref,
            "facts": sorted(facts),
            "knowledge": await self._knowledge_stamp(),
        }
        key = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
        return CacheScope(key=key, vector=await self._embedder.embed_query(question))

    async def lookup(self, scope: CacheScope) -> CacheHit | None:
        distance = SemanticCacheEntry.embedding.cosine_distance(scope.vector)
        fresh_since = datetime.now(UTC) - timedelta(hours=self._config.ttl_hours)
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(SemanticCacheEntry, distance)
                    .where(
                        SemanticCacheEntry.scope_key == scope.key,
                        SemanticCacheEntry.created_at >= fresh_since,
                    )
                    .order_by(distance)
                    .limit(1)
                )
            ).first()
            if row is None:
                return None
            entry, dist = row
            similarity = 1 - float(dist)
            if similarity < self._config.similarity_threshold:
                return None
            await session.execute(
                update(SemanticCacheEntry)
                .where(SemanticCacheEntry.id == entry.id)
                .values(hits=SemanticCacheEntry.hits + 1, last_hit_at=func.now())
            )
            await session.commit()
        return CacheHit(
            question=entry.question,
            answer=entry.answer,
            citations=[CitationEvent.model_validate(c) for c in entry.citations],
            similarity=round(similarity, 3),
            saved_usd=float(entry.cost_usd) if entry.cost_usd is not None else None,
            created_at=entry.created_at,
        )

    async def store(
        self,
        scope: CacheScope,
        question: str,
        answer: str,
        citations: list[CitationEvent],
        model_id: str,
        cost_usd: float | None,
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                SemanticCacheEntry(
                    scope_key=scope.key,
                    question=question,
                    embedding=scope.vector,
                    answer=answer,
                    citations=[c.model_dump() for c in citations],
                    model_id=model_id,
                    cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
                )
            )
            await session.commit()

    async def _knowledge_stamp(self) -> str:
        """Changes whenever any document is ingested, re-ingested, uploaded or deleted, so
        every answer written from the old documents stops matching: no stale answers, and no
        cleanup hook to forget in each place documents change."""
        async with self._session_factory() as session:
            count, latest = (
                await session.execute(select(func.count(), func.max(DocumentRecord.updated_at)))
            ).one()
        return f"{count}:{latest.isoformat() if latest else '-'}"
