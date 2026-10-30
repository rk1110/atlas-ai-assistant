"""Parsers turn a raw Document (any format) into clean text with Markdown-style headings.

Everything after this step (chunking, embedding) only ever sees that one format, so supporting
a new file type means writing one parser and adding it to `parse()`.
"""

from pydantic import BaseModel

from core.interfaces.data_source import Document
from ingestion.parsers.html import html_to_text
from ingestion.parsers.markdown import clean_markdown
from ingestion.parsers.pdf import pdf_to_text


class ParsedDocument(BaseModel):
    title: str
    text: str


class UnsupportedContentError(ValueError):
    pass


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
        case other:
            raise UnsupportedContentError(f"no parser for content type '{other}'")
    if not text.strip():
        hint = " (a scanned PDF needs OCR, Phase 6)" if document.content_type == "pdf" else ""
        raise UnsupportedContentError(f"no text found{hint}")
    # The source's title wins: it comes from front matter or the file name, which are more
    # reliable than a PDF's often-missing metadata.
    return ParsedDocument(title=document.title or title or "Untitled", text=text)


def _as_text(content: str | bytes) -> str:
    return content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
