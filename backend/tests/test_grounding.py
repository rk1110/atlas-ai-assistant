"""Sources block for the prompt, and [n] markers -> citations."""

from services.grounding import NO_SOURCES, citations_for, cited_numbers, format_sources
from tests.conftest import make_chunk

CHUNKS = [make_chunk(1, "22 vacation days."), make_chunk(2, "Meals up to $60."), make_chunk(3, "x")]


def test_sources_are_numbered_from_one_with_title_and_heading():
    text = format_sources(CHUNKS[:2])
    assert text.startswith("[1] Doc 1 > Policy\n22 vacation days.")
    assert "\n\n[2] Doc 2 > Policy\nMeals up to $60." in text


def test_title_is_not_repeated_when_the_heading_already_starts_with_it():
    chunk = make_chunk(1, "16 weeks.")
    chunk.metadata["heading"] = "Doc 1 > How much leave"
    assert format_sources([chunk]).startswith("[1] Doc 1 > How much leave\n")


def test_no_chunks_says_so_instead_of_an_empty_block():
    assert format_sources([]) == NO_SOURCES


def test_cited_numbers_handles_all_marker_styles_in_order_without_duplicates():
    answer = "Fact [2]. Another [1][3]. Both [2, 3]. Again [1]."
    assert cited_numbers(answer, source_count=3) == [2, 1, 3]


def test_gpt_oss_full_width_brackets_count_too():
    assert cited_numbers("Sixteen weeks【1】 and【3†L4-L9】.", source_count=3) == [1, 3]


def test_numbers_without_a_matching_source_are_dropped():
    # The model invented [9]; a [0] is never valid; a Markdown link isn't a citation.
    answer = "See [9] and [0] and [the docs](https://example.com) and [1]."
    assert cited_numbers(answer, source_count=3) == [1]


def test_citations_only_for_cited_sources_with_the_passage_as_snippet():
    citations = citations_for("You get 22 days [1].", CHUNKS)
    assert len(citations) == 1
    c = citations[0]
    assert (c.citation_id, c.document_id, c.heading) == ("1", "acme-docs:doc-1.md", "Policy")
    assert c.snippet == "22 vacation days."
