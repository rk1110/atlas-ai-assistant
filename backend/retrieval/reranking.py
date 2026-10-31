"""Reranking: re-score another retriever's top candidates with a cross-encoder.

    hybrid search ──top 20──▶ cross-encoder reads (question, chunk) pairs ──▶ best 5

Two kinds of model, two jobs:
- A *bi-encoder* (the embedding model) encodes the question and each chunk SEPARATELY. That
  is what makes search fast: chunk vectors are computed once, at ingestion. But the question
  and the chunk never "see" each other, so fine distinctions get lost.
- A *cross-encoder* reads the question and one chunk TOGETHER and outputs one relevance score.
  Much more accurate (it can tell "16 weeks for all parents" answers "how long is paternity
  leave?"), but it must run once per pair at question time, so it can't scan 900 chunks.

So: a cheap, wide first stage finds 20 candidates; the slow, precise model orders them.
"""

from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever
from core.reranker import Reranker


class RerankingRetriever(Retriever):
    def __init__(self, inner: Retriever, reranker: Reranker, *, candidates: int = 20):
        self._inner = inner
        self._reranker = reranker
        self._candidates = candidates
        self.name = f"{inner.name}_rerank"  # e.g. "hybrid_rerank", in traces and eval runs

    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        candidates = await self._inner.retrieve(query, filters, top_k=max(top_k, self._candidates))
        if not candidates:
            return []
        scores = await self._reranker.score(query, [rerank_text(c) for c in candidates])
        ranked = sorted(
            zip(scores, range(1, len(candidates) + 1), candidates, strict=True),
            key=lambda item: item[0],
            reverse=True,
        )
        return [
            chunk.model_copy(
                update={
                    "score": round(score, 4),
                    # Where the first stage had it: "#9 -> #1" is reranking at work.
                    "metadata": {**chunk.metadata, "rank_before_rerank": first_rank},
                }
            )
            for score, first_rank, chunk in ranked[:top_k]
        ]


def rerank_text(chunk: Chunk) -> str:
    """The same context the embedding saw: a passage that says "up to 5 days" needs its title
    and heading ("Time Off Policy > Vacation") to be judged."""
    heading = chunk.metadata.get("heading")
    header = f"{chunk.title} > {heading}" if heading else chunk.title
    return f"{header}\n\n{chunk.text}"
