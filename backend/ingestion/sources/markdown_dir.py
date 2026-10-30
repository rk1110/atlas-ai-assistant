"""DataSources that read a folder of Markdown files: the GitLab handbook and the Acme docs.

They differ only in how a file path becomes a document id and a link, which matters: the id
is what the eval golden set's `expected_sources` refers to, and the URL is where a citation
chip takes you.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import anyio

from core.interfaces.data_source import DataSource, Document
from ingestion.parsers.markdown import split_front_matter


class MarkdownDirectorySource(DataSource):
    """Every `*.md` file under `root`, in a stable (sorted) order."""

    def __init__(self, root: Path, name: str | None = None):
        if name:
            self.name = name  # instance override, e.g. a test source
        self.root = root

    async def load(self) -> AsyncIterator[Document]:
        if not self.root.is_dir():
            raise FileNotFoundError(f"{self.name}: folder not found: {self.root}")
        for path in sorted(self.root.rglob("*.md")):
            relative = path.relative_to(self.root)
            if relative.name.lower() == "readme.md":
                continue
            raw = await anyio.Path(path).read_text(encoding="utf-8")
            meta, _ = split_front_matter(raw)
            yield Document(
                id=f"{self.name}:{self.document_path(relative)}",
                source=self.name,
                title=str(meta.get("title") or _title_from_path(relative)),
                content=raw,  # the parser strips front matter and markup later
                content_type="markdown",
                url=self.url_for(relative),
                metadata={k: v for k, v in meta.items() if isinstance(v, str | int | float)},
            )

    def document_path(self, relative: Path) -> str:
        return relative.as_posix()

    def url_for(self, relative: Path) -> str | None:
        return None


class GitLabHandbookSource(MarkdownDirectorySource):
    """`handbook/values/_index.md` -> id `gitlab-handbook:/handbook/values/`, linking to the
    live page at handbook.gitlab.com (the URL scheme of the Hugo site the files come from)."""

    name = "gitlab-handbook"
    SITE = "https://handbook.gitlab.com"

    def document_path(self, relative: Path) -> str:
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "_index":  # Hugo: a folder's _index.md is the folder's own page
            parts = parts[:-1]
        return "/" + "/".join(parts) + "/"

    def url_for(self, relative: Path) -> str | None:
        return self.SITE + self.document_path(relative)


class AcmeDocsSource(MarkdownDirectorySource):
    """`hr/time-off-policy.md` -> id `acme-docs:hr/time-off-policy.md`. Acme is fictional,
    so there's no website: citation chips open the passage inside Atlas instead."""

    name = "acme-docs"


def _title_from_path(relative: Path) -> str:
    stem = relative.parent.name if relative.stem == "_index" else relative.stem
    return stem.replace("-", " ").replace("_", " ").strip().capitalize() or "Untitled"
