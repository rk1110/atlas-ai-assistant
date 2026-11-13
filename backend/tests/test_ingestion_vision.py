"""Phase 6 checkpoint B: scanned PDFs and images become searchable text at import time.
Rendering is real (pypdfium2 on the Acme scan fixture); the vision model is a fake."""

import struct
import zlib
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from pypdf import PdfReader, PdfWriter

from api.deps import get_prompts
from core.config import REPO_ROOT
from core.db import get_session_factory
from core.interfaces.data_source import Document
from core.multimodal_config import IngestionVisionConfig
from core.rag_config import ChunkingConfig
from core.tracing import Tracer
from ingestion.parsers import UnsupportedContentError, parse, parse_document
from ingestion.parsers.pdf import encode_gray_png, page_texts, render_page_png
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.markdown_dir import AcmeDocsSource
from ingestion.sources.uploads import UploadSource
from ingestion.vision import VisionReader
from models import ChunkRecord
from tests.conftest import FakeEmbedder, FakeGateway
from tests.test_multimodal import PNG

SCAN = (REPO_ROOT / "data/acme/facilities/office-access-policy-scan.pdf").read_bytes()
CHART = (REPO_ROOT / "data/acme/it/support-tickets-q3-2026.png").read_bytes()

# A one-page PDF with a real text layer, written by hand (pypdf rebuilds the missing xref).
TYPED_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 20 100 Td (Typed page one) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\nstartxref\n0\n%%EOF"
)


def typed_then_scanned() -> bytes:
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(TYPED_PDF)))
    writer.append(PdfReader(BytesIO(SCAN)))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def reader(gateway: FakeGateway, max_ocr_pages: int = 20) -> VisionReader:
    config = IngestionVisionConfig(render_dpi=72, max_ocr_pages=max_ocr_pages)
    tracer = Tracer(None, "http://langfuse.test", "atlas")
    return VisionReader(gateway, get_prompts(), tracer, "gemma4-cloud", config)


def doc(content: bytes, content_type: str, title: str = "Office access") -> Document:
    return Document(
        id=f"test:{title}", source="test", title=title, content=content,
        content_type=content_type,  # type: ignore[arg-type]
    )  # fmt: skip


# ---------------------------------------------------------------------- rendering


def test_a_scanned_page_has_no_text_layer_but_renders_to_a_png():
    _, pages = page_texts(SCAN)
    assert pages == [""]
    png = render_page_png(SCAN, 0, dpi=72)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (595, 842)  # A4 in points, at 72 DPI = 1 pixel per point


def test_the_png_encoder_writes_rows_with_a_filter_byte():
    png = encode_gray_png(bytes([0, 255, 9, 128, 64, 9]), width=2, height=2, stride=3)
    idat = png[png.index(b"IDAT") + 4 : png.index(b"IEND") - 8]
    assert zlib.decompress(idat) == bytes([0, 0, 255, 0, 128, 64])  # stride padding dropped


# ---------------------------------------------------------------------- vision reader


async def test_only_pages_without_text_go_to_the_vision_model():
    gateway = FakeGateway(chunks=["## Lost badges\n\nReport within 24 hours."])
    parsed = await parse_document(doc(typed_then_scanned(), "pdf"), reader(gateway))
    assert parsed.text == "Typed page one\n\n## Lost badges\n\nReport within 24 hours."
    [call] = gateway.calls  # one call: the typed page was free
    [message] = call
    assert message.images and message.images[0].media_type == "image/png"
    assert "page 2 of 2" in message.content and '"Office access"' in message.content


async def test_ocr_stops_at_the_page_limit_and_skips_blank_pages():
    gateway = FakeGateway(chunks=["[no text]"])
    two_scans = PdfWriter()
    for _ in range(2):
        two_scans.append(PdfReader(BytesIO(SCAN)))
    out = BytesIO()
    two_scans.write(out)
    with pytest.raises(UnsupportedContentError, match="no text"):
        await parse_document(doc(out.getvalue(), "pdf"), reader(gateway, max_ocr_pages=1))
    assert len(gateway.calls) == 1


async def test_an_image_is_described_with_the_index_prompt():
    gateway = FakeGateway(chunks=["# Tickets\n\n| Category | Tickets |\n| Hardware | 268 |"])
    parsed = await parse_document(doc(CHART, "image", "Support tickets"), reader(gateway))
    assert "| Hardware | 268 |" in parsed.text
    assert parsed.title == "Tickets"  # the title on the image beats the file name
    [[message]] = gateway.calls
    assert "EVERY value" in message.content  # image_index, not the chat image_describe
    assert message.images and message.images[0].media_type == "image/png"


async def test_without_a_vision_model_images_fail_clearly():
    with pytest.raises(UnsupportedContentError, match="vision model"):
        parse(doc(PNG, "image"))
    with pytest.raises(UnsupportedContentError, match="OCR"):
        await parse_document(doc(SCAN, "pdf"), vision=None)


# ---------------------------------------------------------------------- sources + pipeline


async def test_acme_source_loads_scans_and_charts_as_bytes():
    documents = [d async for d in AcmeDocsSource(REPO_ROOT / "data/acme").load()]
    by_id = {d.id: d for d in documents}
    scan = by_id["acme-docs:facilities/office-access-policy-scan.pdf"]
    chart = by_id["acme-docs:it/support-tickets-q3-2026.png"]
    assert (scan.content_type, chart.content_type) == ("pdf", "image")
    assert isinstance(chart.content, bytes) and chart.title == "Support tickets q3 2026"


async def test_an_image_is_chunked_and_embedded_like_text(db: None, fake_embedder: FakeEmbedder):
    gateway = FakeGateway(chunks=["# IT tickets Q3 2026\n\nPassword resets: 412 tickets."])
    chunking = ChunkingConfig(chunk_size=80, chunk_overlap=10, min_chunk_size=5)
    pipeline = IngestionPipeline(fake_embedder, chunking, get_session_factory(), reader(gateway))
    result = await pipeline.ingest_document(doc(CHART, "image", "Tickets"))
    assert (result.outcome, result.chunks) == ("ingested", 1)
    async with get_session_factory()() as session:
        chunk = await session.scalar(
            ChunkRecord.__table__.select().where(ChunkRecord.document_id == "test:Tickets")
        )
    assert chunk is not None


async def test_upload_rejects_a_fake_image(client: AsyncClient, tmp_path: Path):
    from api.deps import get_upload_source
    from main import app

    app.dependency_overrides[get_upload_source] = lambda: UploadSource(tmp_path, [".png", ".md"])
    response = await client.post(
        "/api/knowledge/uploads", files={"file": ("chart.png", b"<svg>not a png</svg>")}
    )
    app.dependency_overrides.pop(get_upload_source)
    assert response.status_code == 415 and "not a valid image" in response.json()["detail"]
