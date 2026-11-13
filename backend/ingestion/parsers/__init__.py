"""Parsers turn a raw Document (any format) into clean text with Markdown-style headings.

Everything after this step (chunking, embedding) only ever sees that one format, so supporting
a new file type means writing one parser and adding it to `parse()`.

`parse()` is plain text extraction. `parse_document()` adds a vision model (Phase 6) for what
has no text layer: scanned PDF pages and images.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel

from core.interfaces.data_source import Document
from ingestion.parsers.html import html_to_text
from ingestion.parsers.markdown import clean_markdown
from ingestion.parsers.pdf import pdf_to_text

if TYPE_CHECKING:
    from ingestion.vision import VisionReader


class ParsedDocument(BaseModel):
    title: str
    text: str


class UnsupportedContentError(ValueError):
    pass


async def parse_document(document: Document, vision: "VisionReader | None") -> ParsedDocument:
    """Like `parse()`, but PDFs and images go through the vision reader when there is one."""
    if vision is None or document.content_type not in ("pdf", "image"):
        return parse(document)
    title, text = await vision.read(document)
    parsed = _finish(document, title, text)
    # A file name ("office-access-policy-scan.pdf") is a poor title; the one printed on the
    # page, which the model transcribed as the first "# " heading, is what people search for.
    heading = _first_title(text)
    return parsed.model_copy(update={"title": heading}) if heading else parsed


def parse(document: Document) -> ParsedDocument:
    content = document.content
    match document.content_type:
        case "markdown" | "text":
            text = clean_markdown(_as_text(content))
            title = None
        case "html":
            title, text = html_to_text(_as_text(content))
        case "pdf":
            if isinstance(content, str):
                raise UnsupportedContentError("PDF content must be bytes")
            title, text = pdf_to_text(content)
        case "image":
            raise UnsupportedContentError("images need a vision model (defaults.vision)")
        case other:
            raise UnsupportedContentError(f"no parser for content type '{other}'")
    return _finish(document, title, text)


def _finish(document: Document, title: str | None, text: str) -> ParsedDocument:
    if not text.strip():
        scan = document.content_type == "pdf"
        hint = " (a scanned PDF needs a vision model for OCR)" if scan else ""
        raise UnsupportedContentError(f"no text found{hint}")
    # The source's title wins: it comes from front matter or the file name, which are more
    # reliable than a PDF's often-missing metadata.
    return ParsedDocument(title=document.title or title or "Untitled", text=text)


def _first_title(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip().strip("*").strip()[:200] or None
    return None


def _as_text(content: str | bytes) -> str:
    return content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
