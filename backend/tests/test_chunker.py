"""The heading-aware chunker, with words as tokens (FakeEmbedder.count_tokens)."""

from core.rag_config import ChunkingConfig
from ingestion.chunkers import MarkdownChunker


def chunker(size: int = 50, overlap: int = 10, min_size: int = 5) -> MarkdownChunker:
    config = ChunkingConfig(chunk_size=size, chunk_overlap=overlap, min_chunk_size=min_size)
    return MarkdownChunker(config, lambda text: len(text.split()))


def words(n: int, word: str = "word") -> str:
    return " ".join(f"{word}{i}" for i in range(n))


def test_sections_carry_their_heading_path():
    text = f"# Values\n\n{words(8)}\n\n## Iteration\n\n{words(8)}\n\n# Mission\n\n{words(8)}"
    chunks = chunker().chunk(text)
    assert [c.heading for c in chunks] == ["Values", "Values > Iteration", "Mission"]


def test_no_chunk_exceeds_the_size_limit():
    text = "\n\n".join(words(30, f"p{i}x") + "." for i in range(10))  # 10 paragraphs of 30 words
    chunks = chunker(size=50, overlap=10).chunk(text)
    assert len(chunks) > 1
    assert all(c.token_count <= 50 for c in chunks)


def test_a_paragraph_that_fits_is_never_split():
    first, second = words(30, "a"), words(30, "b")  # together 60 > 50: must go to 2 chunks
    chunks = chunker(size=50, overlap=0).chunk(f"{first}\n\n{second}")
    assert [c.text for c in chunks] == [first, second]


def test_long_paragraph_splits_on_sentences_with_overlap():
    sentences = [f"Sentence {i} has exactly six words." for i in range(20)]  # 6 words each
    chunks = chunker(size=30, overlap=12).chunk(" ".join(sentences))
    assert len(chunks) > 1
    # Each later chunk starts with the last sentences of the previous one (the overlap).
    last_two_sentences = ". ".join(chunks[0].text.split(". ")[-2:])  # 12 words = the overlap
    assert chunks[1].text.startswith(last_two_sentences)


def test_overlap_never_crosses_into_another_section():
    text = f"# A\n\n{words(45, 'a')}\n\n{words(45, 'a2')}\n\n# B\n\n{words(10, 'b')}"
    chunks = chunker(size=50, overlap=20).chunk(text)
    b_chunk = next(c for c in chunks if c.heading == "B")
    assert "a" not in b_chunk.text.split()[0]


def test_tiny_sections_merge_into_the_previous_chunk():
    text = f"# Policy\n\n{words(20)}\n\n## Contact\n\nEmail hr."
    chunks = chunker(size=50, min_size=5).chunk(text)
    assert len(chunks) == 1
    assert "Contact: Email hr." in chunks[0].text


def test_headings_inside_code_fences_are_not_sections():
    text = "# Real\n\n```\n# not a heading\nprint(1)\n```\n\nAfter the code block, more text."
    chunks = chunker(min_size=0).chunk(text)
    assert {c.heading for c in chunks} == {"Real"}
