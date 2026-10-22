# ingestion/ (Phase 2)

Turns raw documents into searchable chunks: **source → parser → chunker → embedder → pgvector**.

- `sources/` — `DataSource` implementations (`gitlab_handbook.py`, `acme_docs.py`, uploads, `confluence.py` later)
- `parsers/` — PDF, HTML, Markdown, image → clean text + metadata
- `chunkers/` — fixed-size, recursive, semantic chunking strategies (compared with evals)
