"""Grounding: put retrieved chunks into the prompt, and turn the answer's [n] markers into
citations.

    chunks ──format_sources──▶ "[1] Parental leave policy > Eligibility\\n<text>..." (prompt)
    answer "...16 weeks [1]." ──cited_numbers──▶ [1] ──citations_for──▶ CitationEvent(s)

Why numbered markers instead of asking the model for JSON: the answer streams token by token
as plain Markdown, and "[1]" is short, natural for the model, and easy to find afterwards.
We only trust numbers that match a source we actually sent, so a hallucinated "[9]" is dropped
instead of becoming a broken chip.
"""

import re

from core.events import CitationEvent
from core.interfaces.retriever import Chunk

# "[1]", "[2][3]" and "[1, 3]" all count. Markdown links "[text](url)" never match (digits only).
# Also "【1】" and "【1†L4-L9】": OpenAI's gpt-oss models were trained to cite in that style and
# fall back to it even when the prompt shows [1]. Parsing tolerantly beats fighting each model.
CITATION_PATTERN = re.compile(r"[\[【](\d+(?:\s*,\s*\d+)*)(?:†[^\]】]*)?[\]】]")

NO_SOURCES = "(No documents in the knowledge base matched this question.)"


def format_sources(chunks: list[Chunk], start: int = 1) -> str:
    """The numbered sources block for the system prompt. Numbering starts at 1 because the
    model will write these numbers in its answer, and [1] reads better than [0]. The agent
    (Phase 4) passes `start` so numbers keep counting up across several searches."""
    if not chunks:
        return NO_SOURCES
    blocks = []
    for number, chunk in enumerate(chunks, start=start):
        blocks.append(f"[{number}] {source_label(chunk)}\n{chunk.text.strip()}")
    return "\n\n".join(blocks)


def source_label(chunk: Chunk) -> str:
    """'Title > Heading'. Headings often start with the title (the page's own "# Title");
    don't repeat it."""
    heading = chunk.metadata.get("heading")
    if not heading or heading.startswith(chunk.title):
        return heading or chunk.title
    return f"{chunk.title} > {heading}"


def cited_numbers(answer: str, source_count: int) -> list[int]:
    """Source numbers the answer cites, in order of first appearance, ignoring numbers that
    don't refer to a source we sent."""
    seen: list[int] = []
    for match in CITATION_PATTERN.finditer(answer):
        for part in match.group(1).split(","):
            number = int(part)
            if 1 <= number <= source_count and number not in seen:
                seen.append(number)
    return seen


def citations_for(answer: str, chunks: list[Chunk]) -> list[CitationEvent]:
    """One CitationEvent per source the answer actually cites (not every retrieved chunk:
    a chip should mean "this answer relies on this passage")."""
    return [
        CitationEvent(
            citation_id=str(number),
            document_id=chunks[number - 1].document_id,
            title=chunks[number - 1].title,
            heading=chunks[number - 1].metadata.get("heading"),
            url=chunks[number - 1].url,
            snippet=chunks[number - 1].text,
            score=chunks[number - 1].score,
        )
        for number in cited_numbers(answer, len(chunks))
    ]
