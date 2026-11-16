"""Who is asking, for permission-aware retrieval (Phase 7).

Every document carries access tags ("public", "hr"); every user has the tags they may read.
Search must only return documents that share a tag with the user, on *every* path: the chat,
the agent's search_docs tool, the Knowledge page, the MCP server. Passing the user through
each of those by hand would be easy to forget once, which is all a leak takes.

So the request sets the reader's tags in a context variable (a value private to the current
request, even with many requests running concurrently on one event loop), and the retrieval
SQL reads it. Safe by default: with nothing set, only "public" documents are visible. Scripts
that need everything (evals, ingestion checks) say so explicitly with `all_access()`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

PUBLIC = ["public"]
ALL = None  # no restriction

_reader_tags: ContextVar[list[str] | None] = ContextVar("reader_tags", default=PUBLIC)


def reader_tags() -> list[str] | None:
    """The current reader's access tags; None = may read everything."""
    return _reader_tags.get()


def set_reader_tags(tags: list[str] | None) -> None:
    _reader_tags.set(tags)


@contextmanager
def all_access() -> Iterator[None]:
    """For trusted scripts only (evals, admin tools): read every document."""
    token = _reader_tags.set(ALL)
    try:
        yield
    finally:
        _reader_tags.reset(token)
