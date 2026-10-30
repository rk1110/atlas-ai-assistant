"""VectorRetriever against real pgvector (test database), with the fake embedder.

The fake embedder's vectors are bags of words, so "nearest" here means "shares the most
words". That's enough to test the SQL: ordering, scores, filters, and skipping documents
that aren't ready.
"""

from pathlib import Path

from sqlalchemy import update

from core.db import get_session_factory
from core.interfaces.retriever import RetrievalFilters
from core.rag_config import ChunkingConfig
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.markdown_dir import AcmeDocsSource
from models import DocumentRecord
from retrieval.vector import VectorRetriever
from tests.conftest import FakeEmbedder

CHUNKING = ChunkingConfig(chunk_size=80, chunk_overlap=10, min_chunk_size=5)


def write_docs(folder: Path, docs: dict[str, str]) -> None:
    folder.mkdir()
    for name, body in docs.items():
        (folder / name).write_text(f"---\ntitle: {name}\n---\n# Policy\n\n{body}\n")


async def ingest(folder: Path, source_name: str, docs: dict[str, str], embedder: FakeEmbedder):
    write_docs(folder, docs)
    pipeline = IngestionPipeline(embedder, CHUNKING, get_session_factory())
    await pipeline.ingest_source(AcmeDocsSource(folder, name=source_name))


async def test_returns_closest_chunk_first_with_similarity_scores(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    await ingest(
        tmp_path / "hr",
        "hr-docs",
        {
            "leave.md": "Parental leave is sixteen weeks of paid leave.",
            "vacation.md": "Employees get twenty two vacation days per year.",
            "phishing.md": "Report phishing emails to security within one hour.",
        },
        fake_embedder,
    )
    retriever = VectorRetriever(fake_embedder, get_session_factory())

    chunks = await retriever.retrieve("how many vacation days per year", top_k=2)

    assert chunks[0].document_id == "hr-docs:vacation.md"
    assert len(chunks) == 2
    assert chunks[0].score is not None and chunks[1].score is not None
    assert chunks[0].score > chunks[1].score  # best first, higher = more similar
    assert chunks[0].metadata["heading"] == "Policy"
    assert chunks[0].text == "Employees get twenty two vacation days per year."  # no header


async def test_filters_by_source_and_skips_documents_that_are_not_ready(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    await ingest(tmp_path / "a", "source-a", {"x.md": "vacation days policy"}, fake_embedder)
    await ingest(tmp_path / "b", "source-b", {"y.md": "vacation days rules"}, fake_embedder)
    retriever = VectorRetriever(fake_embedder, get_session_factory())

    only_b = await retriever.retrieve("vacation days", RetrievalFilters(sources=["source-b"]))
    assert [c.document_id for c in only_b] == ["source-b:y.md"]

    async with get_session_factory()() as session:  # e.g. mid re-ingestion
        await session.execute(
            update(DocumentRecord)
            .where(DocumentRecord.id == "source-a:x.md")
            .values(status="processing")
        )
        await session.commit()
    everything = await retriever.retrieve("vacation days")
    assert [c.document_id for c in everything] == ["source-b:y.md"]
