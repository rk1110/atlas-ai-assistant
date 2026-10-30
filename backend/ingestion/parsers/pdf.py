"""PDF -> text, page by page.

PDFs store positioned characters, not paragraphs or headings, so extracted text loses most
structure: the chunker falls back to paragraph and sentence splitting. Scanned PDFs (images of
text) give no text at all here; those need OCR, which arrives with multimodal in Phase 6.
"""

from io import BytesIO

from pypdf import PdfReader


def pdf_to_text(data: bytes) -> tuple[str | None, str]:
    """Return (title from the PDF's metadata if any, text)."""
    reader = PdfReader(BytesIO(data))
    title = reader.metadata.title if reader.metadata and reader.metadata.title else None
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return title, "\n\n".join(p for p in pages if p)
