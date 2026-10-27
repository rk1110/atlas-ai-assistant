"""`Retriever`: finds the passages most relevant to a question. Phase 2 (vector) and Phase 3.

Retrieval is the "R" in RAG: before the model answers, we search the knowledge base and put
the best passages into the prompt, so the answer is grounded in real documents and can cite
them. Every retrieval strategy implements the same method, which makes them swappable and
comparable with the eval suite (hit rate, MRR):

    Phase 2: VectorRetriever    - embedding similarity in pgvector ("same meaning")
    Phase 3: KeywordRetriever   - Postgres full-text search ("same words": codes, names)
             HybridRetriever    - runs both and fuses the rankings
             RerankingRetriever - wraps any retriever, re-scores its results with a cross-encoder
             GraphRetriever     - follows entity links in Neo4j (GraphRAG)

Wrappers (hybrid, reranking) take other Retrievers as input: composition, not inheritance.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A passage of a document: the unit we embed, retrieve, put in the prompt and cite."""

    id: str
    document_id: str
    text: str
    title: str  # document title, shown on the citation chip
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None  # relevance; higher = better. Scales differ per retriever.


class RetrievalFilters(BaseModel):
    """Narrow the search before ranking (metadata filtering), e.g. only HR documents."""

    sources: list[str] | None = None  # DataSource names
    metadata: dict[str, Any] = Field(default_factory=dict)  # exact-match filters
    access_tags: list[str] | None = None  # Phase 7: only documents the user may see


class Retriever(ABC):
    name: ClassVar[str]  # e.g. "vector", "hybrid"; recorded in traces and eval results

    @abstractmethod
    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        """Return up to `top_k` chunks, best first."""
