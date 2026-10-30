"""UploadSource: files people upload on the Knowledge Base page.

Uploads are saved into one folder (a Docker volume) and this source reads that folder like any
other DataSource. That's deliberate: the upload endpoint ingests a new file right away, but
`python -m ingestion.run --force` (after changing chunk settings or the embedding model) also
re-embeds uploads, and deleting a file removes its document on the next run.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import anyio

from core.interfaces.data_source import ContentType, DataSource, Document
from ingestion.parsers.markdown import split_front_matter

CONTENT_TYPES: dict[str, ContentType] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
}
UNSAFE_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]+")


class UploadSource(DataSource):
    name = "uploads"

    def __init__(self, root: Path, extensions: list[str], name: str | None = None):
        if name:
            self.name = name
        self.root = root
        self.extensions = {e.lower() for e in extensions if e.lower() in CONTENT_TYPES}

    async def load(self) -> AsyncIterator[Document]:
        if not self.root.is_dir():
            return  # nothing uploaded yet
        for path in sorted(self.root.iterdir()):
            if path.is_file() and path.suffix.lower() in self.extensions:
                yield await self.document(path)

    def safe_filename(self, filename: str) -> str:
        """A name that can't escape the folder ("../../etc/passwd" -> "passwd") or hide
        odd characters. Raises ValueError for types we can't parse."""
        name = UNSAFE_CHARACTERS.sub("-", Path(filename).name).strip(".-")
        if Path(name).suffix.lower() not in self.extensions:
            allowed = ", ".join(sorted(self.extensions))
            raise ValueError(f"'{filename}' is not a supported file type ({allowed})")
        return name

    def document_id(self, filename: str) -> str:
        return f"{self.name}:{filename}"

    async def document(self, path: Path) -> Document:
        content_type = CONTENT_TYPES[path.suffix.lower()]
        raw = await anyio.Path(path).read_bytes()
        content: str | bytes = raw if content_type == "pdf" else raw.decode("utf-8", "replace")
        title = path.stem.replace("-", " ").replace("_", " ").strip() or path.name
        if content_type == "markdown" and isinstance(content, str):
            meta, _ = split_front_matter(content)
            title = str(meta.get("title") or title)
        return Document(
            id=self.document_id(path.name),
            source=self.name,
            title=title,
            content=content,
            content_type=content_type,
            url=None,  # no web page: chips open the passage inside Atlas
        )
