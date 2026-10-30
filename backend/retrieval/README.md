# retrieval/ (Phase 2–3)

`Retriever` implementations: `retrieve(query, filters, top_k) -> list[Chunk]`, best first.

- `vector.py`: `VectorRetriever`, embedding similarity in pgvector (Phase 2).
- `__init__.py`: `get_retriever()`, the one the chat uses.

Phase 3 adds keyword (Postgres full-text), hybrid (fusion), cross-encoder reranker, query rewriting
and a graph retriever (Neo4j). Measure any change with `python -m evals.run --retrieval-only`.
