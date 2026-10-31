"""Hybrid search: run several retrievers and fuse their rankings with Reciprocal Rank Fusion.

    vector  : [A, B, C, D, ...]      RRF score of a chunk = sum over lists of 1 / (k + rank)
    keyword : [C, E, A, F, ...]      A: 1/61 + 1/63   C: 1/63 + 1/61   E: 1/62   B: 1/62 ...

Why RRF and not "add the scores": the scores live on different scales (cosine similarity is
0..1, BM25 is 0..~30 and depends on the query), so adding them lets one retriever drown the
other. RRF only uses *positions*, which are comparable by construction. A chunk near the top
of both lists wins; a chunk only one retriever found still gets in. k (60, from the original
paper) softens the gap between rank 1 and rank 2, so one list can't dominate on its own.

The fused score is divided by the best possible score (rank 1 in every list), so 1.0 means
"first everywhere", which keeps it readable on the 0-1 score bars in the UI.
"""

import asyncio

from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever


class HybridRetriever(Retriever):
    name = "hybrid"

    def __init__(
        self,
        retrievers: list[Retriever],
        *,
        candidates: int = 20,
        rrf_k: int = 60,
        name: str = "hybrid",
    ):
        self.name = name  # type: ignore[misc]  # "hybrid", or "hybrid_graph" with the graph
        self._retrievers = retrievers
        self._candidates = candidates  # how deep each list goes before fusing
        self._rrf_k = rrf_k

    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        # Concurrently: the vector search waits on the embedding model, keyword on Postgres.
        depth = max(top_k, self._candidates)
        rankings = await asyncio.gather(
            *(r.retrieve(query, filters, top_k=depth) for r in self._retrievers)
        )
        return fuse(
            {r.name: ranking for r, ranking in zip(self._retrievers, rankings, strict=True)},
            rrf_k=self._rrf_k,
        )[:top_k]


def fuse(rankings: dict[str, list[Chunk]], *, rrf_k: int = 60) -> list[Chunk]:
    """Reciprocal Rank Fusion. Each fused chunk records which retrievers found it, and where
    (metadata["ranks"], e.g. {"vector": 3, "keyword": 1}): handy for seeing *why* it's there."""
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    ranks: dict[str, dict[str, int]] = {}
    for retriever_name, ranking in rankings.items():
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1 / (rrf_k + rank)
            chunks.setdefault(chunk.id, chunk)
            ranks.setdefault(chunk.id, {})[retriever_name] = rank
    best_possible = len(rankings) / (rrf_k + 1)
    ordered = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [
        chunks[chunk_id].model_copy(
            update={
                "score": round(scores[chunk_id] / best_possible, 4),
                "metadata": {**chunks[chunk_id].metadata, "ranks": ranks[chunk_id]},
            }
        )
        for chunk_id in ordered
    ]
