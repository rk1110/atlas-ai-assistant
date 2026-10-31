# retrieval/ (Phase 2–3)

`Retriever` implementations: `retrieve(query, filters, top_k) -> list[Chunk]`, best first.
The chat uses `retrieval.strategy` from `config/rag.yaml` (today: `hybrid_graph`).

| File | Strategy | Finds by |
| --- | --- | --- |
| `vector.py` | `vector` | meaning: embedding similarity in pgvector |
| `keyword.py` | `keyword` | words: Postgres full-text candidates, ranked with BM25 |
| `hybrid.py` | `hybrid`, `hybrid_graph` | several retrievers fused with Reciprocal Rank Fusion |
| `reranking.py` | `hybrid_rerank` | a cross-encoder (`core/reranker.py`) re-orders the top 10 |
| `graph.py` | `graph` | facts within 2 hops of the entities a question names (Neo4j, `graph/`) |
| `__init__.py` | | `build_retriever(strategy)` and `get_retriever()` |

Query rewriting (follow-ups → standalone questions) happens before retrieval, in
`services/query_rewriter.py`.

Compare strategies for free: `python -m evals.run --retrieval-only --retriever all`.
