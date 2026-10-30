"""The ingestion pipeline: DataSource -> parse -> chunk -> embed -> Postgres.

    for each Document a source yields:
        1. hash the raw content; unchanged since last time -> skip (re-runs are cheap)
        2. parse     any format -> clean text with Markdown headings
        3. chunk     text -> passages of ~350 tokens, each with its heading path
        4. embed     every passage -> a 384-number vector (batched, on CPU)
        5. store     replace the document's old chunks with the new ones, in ONE transaction,
                     so a search never sees a half-updated document
    then: delete documents the source no longer has (renamed or removed files)

A document that fails (unparsable PDF, empty file) is marked `failed` with the reason, and the
run continues: one bad file must not stop a 500-file import.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.embeddings import Embedder
from core.interfaces.data_source import DataSource, Document
from core.rag_config import ChunkingConfig
from ingestion.chunkers import ChunkDraft, MarkdownChunker
from ingestion.parsers import parse
from models import ChunkRecord, DocumentRecord

logger = logging.getLogger(__name__)

Outcome = Literal["ingested", "skipped", "failed"]


@dataclass
class DocumentResult:
    document_id: str
    outcome: Outcome
    chunks: int = 0
    seconds: float = 0.0
    error: str | None = None


@dataclass
class SourceReport:
    source: str
    results: list[DocumentResult] = field(default_factory=list)
    removed: int = 0

    def count(self, outcome: Outcome) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)


class IngestionPipeline:
    def __init__(
        self,
        embedder: Embedder,
        chunking: ChunkingConfig,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self._embedder = embedder
        self._chunker = MarkdownChunker(chunking, embedder.count_tokens)
        self._session_factory = session_factory

    async def ingest_source(
        self,
        source: DataSource,
        *,
        force: bool = False,
        on_result: Callable[[DocumentResult], None] | None = None,
    ) -> SourceReport:
        report = SourceReport(source=source.name)
        seen: set[str] = set()
        async for document in source.load():
            seen.add(document.id)
            result = await self.ingest_document(document, force=force)
            report.results.append(result)
            if on_result:
                on_result(result)
        report.removed = await self._remove_missing(source.name, seen)
        return report

    async def ingest_document(self, document: Document, *, force: bool = False) -> DocumentResult:
        started = time.perf_counter()
        content_hash = _hash(document.content)
        if not force and await self._is_unchanged(document.id, content_hash):
            return DocumentResult(document.id, "skipped")

        await self._upsert_record(document, content_hash, status="processing")
        try:
            parsed = parse(document)
            drafts = self._chunker.chunk(parsed.text)
            vectors = await self._embedder.embed_documents(
                [embedding_text(parsed.title, d) for d in drafts]
            )
            await self._replace_chunks(document.id, parsed.title, drafts, vectors)
        except Exception as exc:  # any failure (logged with traceback): record it, keep going
            logger.exception("ingestion failed for %s", document.id)
            await self._mark_failed(document.id, str(exc))
            return DocumentResult(
                document.id, "failed", seconds=time.perf_counter() - started, error=str(exc)
            )
        return DocumentResult(
            document.id, "ingested", chunks=len(drafts), seconds=time.perf_counter() - started
        )

    async def mark_pending(self, document: Document) -> None:
        """Show a document as "pending" before a background task ingests it, so the Knowledge
        Base page lists it immediately. (If the server restarts before the task runs, it stays
        pending until the next `ingestion.run`, which processes anything not "ready".)"""
        await self._upsert_record(document, _hash(document.content), status="pending")

    # ------------------------------------------------------------------ database steps

    async def _is_unchanged(self, document_id: str, content_hash: str) -> bool:
        async with self._session_factory() as session:
            record = await session.get(DocumentRecord, document_id)
            return (
                record is not None
                and record.status == "ready"
                and (record.content_hash == content_hash)
            )

    async def _upsert_record(self, document: Document, content_hash: str, status: str) -> None:
        async with self._session_factory() as session:
            record = await session.get(DocumentRecord, document.id)
            if record is None:
                record = DocumentRecord(id=document.id)
                session.add(record)
            record.source = document.source
            record.title = document.title
            record.url = document.url
            record.content_type = document.content_type
            record.content_hash = content_hash
            record.metadata_ = document.metadata
            record.access_tags = document.access_tags
            record.status = status
            record.error = None
            await session.commit()

    async def _replace_chunks(
        self,
        document_id: str,
        title: str,
        drafts: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(delete(ChunkRecord).where(ChunkRecord.document_id == document_id))
            session.add_all(
                ChunkRecord(
                    document_id=document_id,
                    ordinal=i,
                    text=draft.text,
                    heading=draft.heading,
                    token_count=draft.token_count,
                    embedding=vector,
                )
                for i, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
            )
            record = await session.get(DocumentRecord, document_id)
            assert record is not None
            record.title = title
            record.status = "ready"
            record.chunk_count = len(drafts)

    async def _mark_failed(self, document_id: str, error: str) -> None:
        async with self._session_factory() as session:
            record = await session.get(DocumentRecord, document_id)
            if record:
                record.status = "failed"
                record.error = error[:1000]
                await session.commit()

    async def _remove_missing(self, source: str, seen: set[str]) -> int:
        """Delete this source's documents that it no longer yields (chunks cascade)."""
        async with self._session_factory() as session:
            ids = await session.scalars(
                select(DocumentRecord.id).where(DocumentRecord.source == source)
            )
            stale = [i for i in ids if i not in seen]
            if stale:
                await session.execute(delete(DocumentRecord).where(DocumentRecord.id.in_(stale)))
                await session.commit()
            return len(stale)


def embedding_text(title: str, draft: ChunkDraft) -> str:
    """What we actually embed: the chunk *plus* where it comes from.

    "Up to 5 unused days can be carried over" alone doesn't say days of *what*. Prefixing the
    document title and heading path ("Time Off Policy / Vacation") puts that context into the
    vector, so the chunk matches questions about vacation. (Known as contextual chunk
    headers.) The stored `text` stays clean for citations; only the vector gets the prefix.
    """
    header = f"{title} / {draft.heading}" if draft.heading else title
    return f"{header}\n\n{draft.text}"


def _hash(content: str | bytes) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()
