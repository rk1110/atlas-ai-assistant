"""PDF -> text, page by page.

PDFs store positioned characters, not paragraphs or headings, so extracted text loses most
structure: the chunker falls back to paragraph and sentence splitting.

Scanned PDFs (photos of paper) have no text layer at all: `page_texts` returns "" for those
pages. Phase 6 renders such a page to an image (`render_page_png`) and lets a vision model read
it (OCR); see `ingestion/vision.py`.
"""

import struct
import zlib
from io import BytesIO

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pypdf import PdfReader


def pdf_to_text(data: bytes) -> tuple[str | None, str]:
    """Return (title from the PDF's metadata if any, text). Text layer only, no OCR."""
    title, pages = page_texts(data)
    return title, "\n\n".join(p for p in pages if p)


def page_texts(data: bytes) -> tuple[str | None, list[str]]:
    """Return (title, the text layer of each page). A scanned page gives ""."""
    reader = PdfReader(BytesIO(data))
    title = reader.metadata.title if reader.metadata and reader.metadata.title else None
    return title, [(page.extract_text() or "").strip() for page in reader.pages]


def render_page_png(data: bytes, index: int, dpi: int) -> bytes:
    """Render one page to a grayscale PNG for a vision model.

    Why grayscale: OCR doesn't need colour, and one byte per pixel makes the image a third
    of the size. Why ~150 DPI: enough for small print to stay readable; much higher only adds
    image tokens. pypdfium2 is PDFium, the PDF engine inside Chrome.
    """
    document = pdfium.PdfDocument(data)
    try:
        bitmap = document[index].render(
            scale=dpi / 72,  # PDF units are points: 72 per inch
            grayscale=True,
            force_bitmap_format=pdfium_c.FPDFBitmap_Gray,
        )
        rows = bytes(bitmap.buffer)
        return encode_gray_png(rows, bitmap.width, bitmap.height, bitmap.stride)
    finally:
        document.close()


def encode_gray_png(pixels: bytes, width: int, height: int, stride: int) -> bytes:
    """A minimal PNG encoder (8-bit grayscale), so we don't need Pillow just for this.

    A PNG is a signature plus chunks (header, compressed pixel rows, end). Each row starts
    with a filter byte; 0 means "no filter".
    """

    def chunk(kind: bytes, body: bytes) -> bytes:
        checksum = struct.pack(">I", zlib.crc32(kind + body))
        return struct.pack(">I", len(body)) + kind + body + checksum

    raw = b"".join(b"\x00" + pixels[y * stride : y * stride + width] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit, colour type 0 = gray
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
