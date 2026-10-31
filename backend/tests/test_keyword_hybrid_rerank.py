"""Phase 3 retrieval: BM25 keyword search (real Postgres), RRF fusion and reranking (pure)."""

from pathlib import Path

from core.db import get_session_factory
from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever
from core.reranker import Reranker
from retrieval.hybrid import HybridRetriever, fuse
from retrieval.keyword import KeywordRetriever, _Stats, bm25
from retrieval.reranking import RerankingRetriever, rerank_text
from tests.conftest import FakeEmbedder, make_chunk
from tests.test_retrieval import ingest

# ---------------------------------------------------------------- keyword (BM25)


async def test_keyword_search_finds_the_exact_rare_term(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    await ingest(
        tmp_path / "docs",
        "handbook",
        {
            "values.md": "Ship a minimal valuable change, an MVC, as early as possible.",
            "remote.md": "GitLab is all remote. GitLab team members work from anywhere.",
            "async.md": "GitLab prefers asynchronous communication over meetings at GitLab.",
        },
        fake_embedder,
    )
    retriever = KeywordRetriever(get_session_factory())

    chunks = await retriever.retrieve("What is an MVC at GitLab?", top_k=3)

    # 'gitlab' appears in more chunks (and more often) but 'mvc' is rare: IDF makes it win.
    assert chunks[0].document_id == "handbook:values.md"
    assert chunks[0].score is not None and chunks[0].score > (chunks[1].score or 0)


async def test_keyword_search_stems_words_and_respects_filters(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    await ingest(tmp_path / "a", "acme", {"meals.md": "Expensed meals are paid."}, fake_embedder)
    await ingest(tmp_path / "b", "other", {"bills.md": "Expenses need receipts."}, fake_embedder)
    retriever = KeywordRetriever(get_session_factory())

    # "expensing", "expensed" and "expenses" all stem to "expens".
    found = await retriever.retrieve("expensing", RetrievalFilters(sources=["acme"]))
    assert [c.document_id for c in found] == ["acme:meals.md"]
    assert len(await retriever.retrieve("expensing")) == 2
    assert await retriever.retrieve("what is it?") == []  # only stop words: nothing to match


def test_bm25_rewards_rare_terms_and_saturates_repeats():
    stats = _Stats(total=100, average_length=10)
    frequency = {"mvc": 2, "gitlab": 90}
    rare = bm25(["mvc", "gitlab"], {"mvc": 1}, frequency, stats)
    common = bm25(["mvc", "gitlab"], {"gitlab": 1}, frequency, stats)
    assert rare > 5 * common
    once = bm25(["mvc"], {"mvc": 1}, frequency, stats)
    five = bm25(["mvc"], {"mvc": 5}, frequency, stats)
    assert once < five < 2.2 * once  # more mentions help, with diminishing returns


# ---------------------------------------------------------------- hybrid (RRF)


def test_fuse_prefers_chunks_ranked_well_by_both_lists():
    a, b, c, d = (make_chunk(n, f"text {n}") for n in range(1, 5))
    fused = fuse({"vector": [a, b, c], "keyword": [c, d, a]})

    assert [chunk.id for chunk in fused][:2] in (["chunk-1", "chunk-3"], ["chunk-3", "chunk-1"])
    assert fused[0].metadata["ranks"].keys() == {"vector", "keyword"}
    by_id = {chunk.id: chunk for chunk in fused}
    assert by_id["chunk-4"].metadata["ranks"] == {"keyword": 2}  # found by one list only
    assert by_id["chunk-1"].score is not None and by_id["chunk-1"].score <= 1.0


def test_fuse_top_of_every_list_scores_one():
    a = make_chunk(1, "text")
    assert fuse({"vector": [a], "keyword": [a]})[0].score == 1.0


class ScriptedRetriever(Retriever):
    def __init__(self, name: str, chunks: list[Chunk]):
        self.name = name  # type: ignore[misc]
        self.chunks = chunks
        self.depths: list[int] = []

    async def retrieve(self, query, filters=None, top_k=5):
        self.depths.append(top_k)
        return self.chunks[:top_k]


async def test_hybrid_asks_each_retriever_for_candidates_and_returns_top_k():
    chunks = [make_chunk(n, f"text {n}") for n in range(1, 8)]
    vector = ScriptedRetriever("vector", chunks)
    keyword = ScriptedRetriever("keyword", chunks[::-1])
    hybrid = HybridRetriever([vector, keyword], candidates=20)

    result = await hybrid.retrieve("q", top_k=3)

    assert len(result) == 3 and vector.depths == [20] and keyword.depths == [20]


# ---------------------------------------------------------------- reranking


class WordOverlapReranker(Reranker):
    """Scores by how many query words a text contains: predictable, like a tiny cross-encoder."""

    async def score(self, query: str, texts: list[str]) -> list[float]:
        words = set(query.lower().split())
        return [len(words & set(t.lower().split())) / len(words) for t in texts]


async def test_reranking_reorders_candidates_and_records_where_they_were():
    first_stage = [
        make_chunk(1, "Office plants are watered on Mondays."),
        make_chunk(2, "Parents get sixteen weeks of paid parental leave."),
    ]
    reranking = RerankingRetriever(
        ScriptedRetriever("hybrid", first_stage), WordOverlapReranker(), candidates=10
    )

    result = await reranking.retrieve("paid parental leave weeks", top_k=1)

    assert reranking.name == "hybrid_rerank"
    assert result[0].id == "chunk-2"
    assert result[0].metadata["rank_before_rerank"] == 2  # moved from #2 to #1
    assert result[0].score == 0.75  # the reranker's score replaces the first-stage one


def test_rerank_text_includes_title_and_heading():
    assert rerank_text(make_chunk(1, "Up to 5 days.")) == "Doc 1 > Policy\n\nUp to 5 days."
