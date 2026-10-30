"""Knowledge Base API: upload -> background ingestion -> list, chunks, search, delete.

httpx's in-process transport waits for FastAPI's background tasks before returning, so right
after the upload request the document is already ingested: no polling or sleeps in tests.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from api.deps import get_ingestion_pipeline, get_rag_config, get_upload_source
from core.db import get_session_factory
from core.rag_config import ChunkingConfig, RagConfig
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.uploads import UploadSource
from main import app
from models import DocumentRecord
from retrieval import get_retriever
from retrieval.vector import VectorRetriever
from tests.conftest import FakeEmbedder

POLICY = b"---\ntitle: Pet Policy\n---\n# Pets\n\nDogs are welcome in the office on Fridays.\n"


@pytest.fixture
async def kb(
    client: AsyncClient, tmp_path: Path, fake_embedder: FakeEmbedder
) -> AsyncIterator[tuple[AsyncClient, UploadSource]]:
    source = UploadSource(tmp_path / "uploads", [".md", ".txt", ".pdf"])
    chunking = ChunkingConfig(chunk_size=80, chunk_overlap=10, min_chunk_size=5)
    config = get_rag_config().model_copy(update={"chunking": chunking})
    config.uploads = config.uploads.model_copy(update={"max_file_mb": 0.001})  # ~1 KB
    app.dependency_overrides[get_upload_source] = lambda: source
    app.dependency_overrides[get_rag_config] = lambda: config
    app.dependency_overrides[get_ingestion_pipeline] = lambda: IngestionPipeline(
        fake_embedder, chunking, get_session_factory()
    )
    app.dependency_overrides[get_retriever] = lambda: VectorRetriever(
        fake_embedder, get_session_factory()
    )
    yield client, source


async def upload(client: AsyncClient, name: str, content: bytes):
    return await client.post("/api/knowledge/uploads", files={"file": (name, content)})


async def test_upload_is_ingested_and_shows_up_everywhere(kb: tuple[AsyncClient, UploadSource]):
    client, source = kb
    response = await upload(client, "pet-policy.md", POLICY)
    assert response.status_code == 202
    assert response.json()["status"] == "pending"  # returned before ingestion ran
    assert (source.root / "pet-policy.md").read_bytes() == POLICY

    [doc] = (await client.get("/api/knowledge/documents")).json()
    assert (doc["id"], doc["title"], doc["status"]) == (
        "uploads:pet-policy.md",
        "Pet Policy",
        "ready",
    )
    assert doc["chunk_count"] == 1

    detail = (await client.get("/api/knowledge/chunks", params={"document_id": doc["id"]})).json()
    assert detail["chunks"][0]["heading"] == "Pets"
    assert "Dogs are welcome" in detail["chunks"][0]["text"]

    found = (await client.get("/api/knowledge/search", params={"q": "dogs in the office"})).json()
    assert found["chunks"][0]["document_id"] == "uploads:pet-policy.md"


async def test_rejects_unsupported_too_large_and_empty_files(kb: tuple[AsyncClient, UploadSource]):
    client, _ = kb
    assert (await upload(client, "virus.exe", b"MZ")).status_code == 415
    assert (await upload(client, "big.md", b"x" * 2000)).status_code == 413
    assert (await upload(client, "empty.md", b"")).status_code == 422
    assert (await client.get("/api/knowledge/documents")).json() == []


async def test_filename_cannot_escape_the_uploads_folder(kb: tuple[AsyncClient, UploadSource]):
    client, source = kb
    response = await upload(client, "../../secret notes.md", POLICY)
    assert response.json()["id"] == "uploads:secret-notes.md"
    assert (source.root / "secret-notes.md").exists()


async def test_unreadable_pdf_is_marked_failed_with_a_reason(kb: tuple[AsyncClient, UploadSource]):
    client, _ = kb
    await upload(client, "broken.pdf", b"%PDF-1.4 not really a pdf")
    [doc] = (await client.get("/api/knowledge/documents")).json()
    assert doc["status"] == "failed" and doc["error"]


async def test_only_uploads_can_be_deleted(kb: tuple[AsyncClient, UploadSource]):
    client, source = kb
    await upload(client, "pet-policy.md", POLICY)
    params = {"document_id": "uploads:pet-policy.md"}
    assert (await client.delete("/api/knowledge/documents", params=params)).status_code == 204
    assert not (source.root / "pet-policy.md").exists()
    assert (await client.get("/api/knowledge/documents")).json() == []

    missing = {"document_id": "acme-docs:hr/x.md"}
    assert (await client.delete("/api/knowledge/documents", params=missing)).status_code == 404

    async with get_session_factory()() as session:  # a document from data/, not an upload
        session.add(
            DocumentRecord(id="acme-docs:hr/x.md", source="acme-docs", title="X",
                           content_type="markdown", content_hash="h", status="ready")
        )  # fmt: skip
        await session.commit()
    assert (await client.delete("/api/knowledge/documents", params=missing)).status_code == 403


async def test_config_comes_from_rag_yaml(kb: tuple[AsyncClient, UploadSource]):
    client, _ = kb
    config = (await client.get("/api/knowledge/config")).json()
    assert ".pdf" in config["upload_extensions"] and config["top_k"] == 5


def test_uploads_folder_is_a_configured_source():
    config = RagConfig.from_file(Path(__file__).resolve().parents[2] / "config" / "rag.yaml")
    uploads = config.source_of_kind("uploads")
    assert uploads is not None and uploads.name == "uploads"
