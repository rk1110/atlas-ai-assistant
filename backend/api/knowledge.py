"""The Knowledge Base API: list documents, inspect their chunks, upload, delete, test search.

    GET    /api/knowledge/config                         upload limits + top_k, for the UI
    GET    /api/knowledge/documents                      every document with status + chunk count
    GET    /api/knowledge/chunks?document_id=...         one document's chunks, in order
    POST   /api/knowledge/uploads        (multipart)     save a file, ingest it in the background
    DELETE /api/knowledge/documents?document_id=...      uploads only
    GET    /api/knowledge/search?q=...                   what retrieval returns for a query

Document ids contain ":" and "/" (e.g. "gitlab-handbook:/handbook/values/"), so they travel
as query parameters rather than path segments.

Why a background task for uploads: parsing + embedding a long PDF takes seconds to minutes.
The request returns at once (202 Accepted) with the document marked "pending"; the page polls
the document list until it turns "ready" or "failed". FastAPI's BackgroundTasks run after the
response, in the same process; Phase 7 can move this to a Redis job queue if it needs
retries or several workers.
"""

from datetime import datetime

import anyio
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import IngestionPipelineDep, RagConfigDep, RetrieverDep, SessionDep, UploadSourceDep
from core.interfaces.retriever import Chunk
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.uploads import UploadSource
from models import ChunkRecord, DocumentRecord

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class DocumentOut(BaseModel):
    id: str
    source: str
    title: str
    url: str | None
    content_type: str
    status: str  # pending | processing | ready | failed
    error: str | None
    chunk_count: int
    updated_at: datetime


class ChunkOut(BaseModel):
    ordinal: int
    heading: str | None
    text: str
    token_count: int


class DocumentDetail(BaseModel):
    document: DocumentOut
    chunks: list[ChunkOut]


class KnowledgeConfig(BaseModel):
    upload_source: str  # documents from this source can be deleted
    upload_extensions: list[str]
    max_file_mb: float
    top_k: int
    embedding_model: str


class SearchResponse(BaseModel):
    retriever: str
    chunks: list[Chunk]


@router.get("/config")
async def knowledge_config(config: RagConfigDep, source: UploadSourceDep) -> KnowledgeConfig:
    """So the page's file picker and hints come from config/rag.yaml, not hard-coded values."""
    return KnowledgeConfig(
        upload_source=source.name,
        upload_extensions=config.uploads.extensions,
        max_file_mb=config.uploads.max_file_mb,
        top_k=config.retrieval.top_k,
        embedding_model=config.embedding.model,
    )


@router.get("/documents")
async def list_documents(session: SessionDep) -> list[DocumentOut]:
    rows = await session.scalars(
        select(DocumentRecord).order_by(DocumentRecord.source, DocumentRecord.title)
    )
    return [_document_out(d) for d in rows.all()]


@router.get("/chunks")
async def document_chunks(session: SessionDep, document_id: str = Query()) -> DocumentDetail:
    document = await _get_document(session, document_id)
    rows = await session.scalars(
        select(ChunkRecord)
        .where(ChunkRecord.document_id == document_id)
        .order_by(ChunkRecord.ordinal)
    )
    chunks = [
        ChunkOut(ordinal=c.ordinal, heading=c.heading, text=c.text, token_count=c.token_count)
        for c in rows.all()
    ]
    return DocumentDetail(document=_document_out(document), chunks=chunks)


@router.post("/uploads", status_code=status.HTTP_202_ACCEPTED)
async def upload(
    file: UploadFile,
    background: BackgroundTasks,
    session: SessionDep,
    source: UploadSourceDep,
    pipeline: IngestionPipelineDep,
    config: RagConfigDep,
) -> DocumentOut:
    try:
        filename = source.safe_filename(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    max_bytes = int(config.uploads.max_file_mb * 1024 * 1024)
    content = await file.read(max_bytes + 1)  # read one byte past the limit to detect "too big"
    if len(content) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File is larger than {config.uploads.max_file_mb} MB",
        )
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")

    path = source.root / filename
    await anyio.Path(source.root).mkdir(parents=True, exist_ok=True)
    await anyio.Path(path).write_bytes(content)  # same name again = replace the document (same id)
    document = await source.document(path)
    await pipeline.mark_pending(document)
    background.add_task(_ingest_in_background, pipeline, source, filename)
    return _document_out(await _get_document(session, document.id, refresh=True))


@router.delete("/documents", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    session: SessionDep, source: UploadSourceDep, document_id: str = Query()
) -> None:
    document = await _get_document(session, document_id)
    if document.source != source.name:
        # Other sources come from data/ and would reappear on the next ingestion run.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only uploaded documents can be deleted")
    filename = document_id.removeprefix(f"{source.name}:")
    await anyio.Path(source.root / filename).unlink(missing_ok=True)
    await session.delete(document)  # chunks go too (ON DELETE CASCADE)
    await session.commit()


@router.get("/search")
async def search(
    retriever: RetrieverDep, config: RagConfigDep, q: str = Query(min_length=2, max_length=500)
) -> SearchResponse:
    """Retrieval alone, no LLM: shows exactly what the chat would put in the prompt."""
    chunks = await retriever.retrieve(q, top_k=config.retrieval.top_k)
    return SearchResponse(retriever=retriever.name, chunks=chunks)


async def _ingest_in_background(
    pipeline: IngestionPipeline, source: UploadSource, filename: str
) -> None:
    # Re-read the file: the request's objects are gone once the response is sent.
    document = await source.document(source.root / filename)
    await pipeline.ingest_document(document, force=True)  # failures are recorded on the row


async def _get_document(
    session: AsyncSession, document_id: str, refresh: bool = False
) -> DocumentRecord:
    document = await session.get(DocumentRecord, document_id, populate_existing=refresh)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


def _document_out(d: DocumentRecord) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        source=d.source,
        title=d.title,
        url=d.url,
        content_type=d.content_type,
        status=d.status,
        error=d.error,
        chunk_count=d.chunk_count,
        updated_at=d.updated_at,
    )
