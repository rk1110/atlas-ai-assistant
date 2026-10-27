"""`DataSource`: where knowledge comes from. Implemented in Phase 2 (ingestion).

A data source only knows how to *fetch* documents from one place (a folder of Markdown, the
GitLab handbook, Confluence, user uploads). It does not parse, chunk or embed; the ingestion
pipeline does that for every source the same way:

    DataSource.load() -> Document -> parser -> chunker -> embedder -> pgvector

So adding Confluence later is one new file, `ingestion/sources/confluence.py`, implementing
this class; nothing else in the pipeline changes (principle 3).
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

ContentType = Literal["markdown", "html", "pdf", "text", "image"]


class Document(BaseModel):
    """One raw document, exactly as fetched from its source (before parsing/chunking)."""

    id: str  # stable across re-ingestion, e.g. "gitlab-handbook:/handbook/values/"
    source: str  # the DataSource.name that produced it
    title: str
    content: str | bytes  # text formats as str; PDFs and images as bytes
    content_type: ContentType
    url: str | None = None  # where a citation chip should link to
    updated_at: datetime | None = None  # lets re-ingestion skip unchanged documents
    metadata: dict[str, Any] = Field(default_factory=dict)  # e.g. {"team": "hr"}, used by filters
    # Who may see this document. Phase 7 permission-aware retrieval filters on these.
    access_tags: list[str] = Field(default_factory=lambda: ["public"])


class DataSource(ABC):
    """A place documents come from.

    Phase 2 implementations: `GitLabHandbookSource`, `AcmeDocsSource`, `UploadSource`.
    Later, for example: `ConfluenceSource`.
    """

    name: ClassVar[str]  # unique, stored on every Document, e.g. "gitlab-handbook"

    @abstractmethod
    def load(self) -> AsyncIterator[Document]:
        """Yield documents one at a time.

        An async iterator (not a list) so a source with thousands of pages streams through
        the pipeline without loading everything into memory first. Implement it as an
        `async def load(self): ... yield doc` generator.
        """
