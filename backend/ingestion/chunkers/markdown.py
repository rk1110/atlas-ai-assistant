"""Heading-aware recursive chunking.

Why chunk at all: an embedding is one vector for a whole text. A 5,000-word page about
"values" squashed into one vector is a blurry average of everything on it, so a question about
one detail (what is an MVC?) matches it weakly. Small passages each get a sharp vector, and
the model gets just the relevant part in its prompt, not the whole page.

Why this strategy ("recursive", splitting on the biggest natural boundary first):

    1. Headings      -> each section stays about one topic, and we remember its heading path
                        ("Values > Iteration") to give every chunk context.
    2. Paragraphs    -> a paragraph that fits is never cut in half.
    3. Sentences     -> only a paragraph too big for one chunk is split into sentences.
    4. Words         -> last resort, for a single enormous "sentence" (tables, long lists).

Sizes are measured in tokens of the embedding model (`count_tokens`), because that's the
model's real limit: BGE reads 512 tokens and silently ignores the rest.

Overlap: each new chunk inside a section starts with the last ~50 tokens of the previous
one, so a fact spanning a boundary is still complete in at least one chunk.

Alternatives (Phase 3 exercise material): fixed-size windows (simplest, cuts mid-sentence),
semantic chunking (split where the embedding of consecutive sentences changes topic).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from core.rag_config import ChunkingConfig

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(\[*])")


@dataclass
class ChunkDraft:
    text: str
    heading: str | None  # "Values > Iteration", or None before the first heading
    token_count: int


@dataclass
class _Section:
    heading: str | None
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class _Piece:
    """A paragraph or sentence on its way into a chunk."""

    text: str
    tokens: int
    starts_paragraph: bool  # joined with a blank line (True) or a space (False)


class MarkdownChunker:
    def __init__(self, config: ChunkingConfig, count_tokens: Callable[[str], int]):
        self.size = config.chunk_size
        self.overlap = config.chunk_overlap
        self.min_size = config.min_chunk_size
        self.count = count_tokens  # injected: the real tokenizer in the app, a fake in tests

    def chunk(self, text: str) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for section in _split_sections(text):
            drafts.extend(self._chunk_section(section))
        return self._merge_small(drafts)

    # ------------------------------------------------------------------ one section

    def _chunk_section(self, section: _Section) -> list[ChunkDraft]:
        chunks: list[list[_Piece]] = []
        current: list[_Piece] = []
        has_new = False  # does `current` hold anything beyond the overlap carried over?

        def flush() -> None:
            nonlocal current, has_new
            if has_new:
                chunks.append(current)
                current = self._overlap_tail(current)
            has_new = False

        def add(piece: _Piece) -> None:
            nonlocal has_new
            if _tokens(current) + piece.tokens > self.size:
                flush()
                if _tokens(current) + piece.tokens > self.size:
                    current.clear()  # the overlap itself doesn't fit next to this piece
            current.append(piece)
            has_new = True

        for paragraph in section.paragraphs:
            tokens = self.count(paragraph)
            if tokens <= self.size:
                if _tokens(current) + tokens > self.size:
                    flush()  # move the whole paragraph to the next chunk rather than cut it
                add(_Piece(paragraph, tokens, starts_paragraph=True))
                continue
            for i, sentence in enumerate(self._sentences(paragraph)):
                add(_Piece(sentence, self.count(sentence), starts_paragraph=i == 0))
        if has_new:
            chunks.append(current)

        return [self._draft(pieces, section.heading) for pieces in chunks]

    def _sentences(self, paragraph: str) -> list[str]:
        """Split an over-long paragraph: lines first (lists, tables), then sentences, then
        fixed word windows for anything still too long."""
        out: list[str] = []
        for line in paragraph.split("\n"):
            for sentence in SENTENCE_END.split(line):
                if not sentence.strip():
                    continue
                if self.count(sentence) <= self.size:
                    out.append(sentence)
                else:
                    out.extend(self._word_windows(sentence))
        return out

    def _word_windows(self, text: str) -> list[str]:
        words, window, out = text.split(), [], []
        for word in words:
            window.append(word)
            if self.count(" ".join(window)) > self.size:
                window.pop()
                out.append(" ".join(window))
                window = [word]
        if window:
            out.append(" ".join(window))
        return out

    def _overlap_tail(self, pieces: list[_Piece]) -> list[_Piece]:
        """The last pieces of a chunk, up to `overlap` tokens, to start the next one with."""
        tail: list[_Piece] = []
        for piece in reversed(pieces):
            if _tokens(tail) + piece.tokens > self.overlap:
                break
            tail.insert(0, piece)
        return tail

    def _draft(self, pieces: list[_Piece], heading: str | None) -> ChunkDraft:
        text = ""
        for piece in pieces:
            if text:
                text += "\n\n" if piece.starts_paragraph else " "
            text += piece.text
        return ChunkDraft(text=text, heading=heading, token_count=self.count(text))

    # ------------------------------------------------------------------ whole document

    def _merge_small(self, drafts: list[ChunkDraft]) -> list[ChunkDraft]:
        """Fold tiny chunks (a heading with one line under it) into the previous chunk when
        they fit: a 10-token chunk makes a poor, noisy search target on its own."""
        merged: list[ChunkDraft] = []
        for draft in drafts:
            previous = merged[-1] if merged else None
            if (
                previous
                and draft.token_count < self.min_size
                and previous.token_count + draft.token_count <= self.size
            ):
                label = draft.heading.split(" > ")[-1] if draft.heading else ""
                joined = f"{previous.text}\n\n{label}: {draft.text}" if label else draft.text
                merged[-1] = ChunkDraft(joined, previous.heading, self.count(joined))
            else:
                merged.append(draft)
        return merged


def _split_sections(text: str) -> list[_Section]:
    """Split on Markdown headings, outside code fences, tracking the heading path."""
    sections = [_Section(heading=None)]
    path: list[tuple[int, str]] = []  # (level, title) of the headings we're inside
    buffer: list[str] = []
    in_code = False

    def close_paragraph() -> None:
        paragraph = "\n".join(buffer).strip()
        if paragraph:
            sections[-1].paragraphs.append(paragraph)
        buffer.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        match = None if in_code else HEADING.match(line)
        if match:
            close_paragraph()
            level, title = len(match.group(1)), match.group(2).strip()
            path = [(lvl, t) for lvl, t in path if lvl < level] + [(level, title)]
            sections.append(_Section(heading=" > ".join(t for _, t in path)))
        elif not line.strip() and not in_code:
            close_paragraph()
        else:
            buffer.append(line)
    close_paragraph()
    return [s for s in sections if s.paragraphs]


def _tokens(pieces: list[_Piece]) -> int:
    return sum(p.tokens for p in pieces)
