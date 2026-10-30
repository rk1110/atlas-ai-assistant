"""The ingestion pipeline against the test database, with the fake embedder."""

from pathlib import Path

from sqlalchemy import func, select

from core.db import get_session_factory
from core.rag_config import ChunkingConfig
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.markdown_dir import AcmeDocsSource
from models import ChunkRecord, DocumentRecord
from tests.conftest import FakeEmbedder

CHUNKING = ChunkingConfig(chunk_size=80, chunk_overlap=10, min_chunk_size=5)


def pipeline(embedder: FakeEmbedder) -> IngestionPipeline:
    return IngestionPipeline(embedder, CHUNKING, get_session_factory())


def write(folder: Path, name: str, body: str) -> None:
    (folder / name).write_text(f"---\ntitle: {name}\nteam: hr\n---\n# Policy\n\n{body}\n")


async def counts() -> tuple[int, int]:
    async with get_session_factory()() as session:
        docs = await session.scalar(select(func.count()).select_from(DocumentRecord))
        chunks = await session.scalar(select(func.count()).select_from(ChunkRecord))
        return docs or 0, chunks or 0


async def test_ingest_then_skip_unchanged_then_update_then_prune(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    write(tmp_path, "a.md", "You get 22 vacation days.")
    write(tmp_path, "b.md", "Report phishing within 1 hour.")
    source = AcmeDocsSource(tmp_path, name="test-docs")
    p = pipeline(fake_embedder)

    first = await p.ingest_source(source)
    assert first.count("ingested") == 2 and await counts() == (2, 2)

    again = await p.ingest_source(source)
    assert again.count("skipped") == 2  # same content hash: no re-embedding
    assert len(fake_embedder.calls) == 2

    write(tmp_path, "a.md", "You get 25 vacation days.")
    (tmp_path / "b.md").unlink()
    third = await p.ingest_source(source)
    assert third.count("ingested") == 1 and third.removed == 1
    async with get_session_factory()() as session:
        text = await session.scalar(select(ChunkRecord.text))
    assert text == "You get 25 vacation days."
    assert await counts() == (1, 1)


async def test_chunks_store_heading_and_vectors_include_the_title(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    write(tmp_path, "leave.md", "16 weeks of paid leave.")
    await pipeline(fake_embedder).ingest_source(AcmeDocsSource(tmp_path, name="test-docs"))

    async with get_session_factory()() as session:
        chunk = await session.scalar(select(ChunkRecord))
        record = await session.get(DocumentRecord, "test-docs:leave.md")
    assert chunk is not None and chunk.heading == "Policy" and len(chunk.embedding) == 384
    assert record is not None and record.status == "ready" and record.metadata_["team"] == "hr"
    assert fake_embedder.calls[0] == ["leave.md / Policy\n\n16 weeks of paid leave."]


async def test_a_bad_document_is_marked_failed_and_the_run_continues(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    (tmp_path / "empty.md").write_text("---\ntitle: Empty\n---\n")
    write(tmp_path, "ok.md", "Fine.")
    report = await pipeline(fake_embedder).ingest_source(AcmeDocsSource(tmp_path, name="t"))

    assert report.count("failed") == 1 and report.count("ingested") == 1
    async with get_session_factory()() as session:
        failed = await session.get(DocumentRecord, "t:empty.md")
    assert failed is not None and failed.status == "failed" and "no text" in (failed.error or "")
