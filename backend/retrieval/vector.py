"""Vector search: find the chunks whose embeddings are closest to the question's embedding.

    question ──embed_query──▶ [0.12, -0.03, ...] ──pgvector `<=>`──▶ 5 nearest chunks

`<=>` is pgvector's cosine *distance* (0 = same direction, 2 = opposite). We return
`1 - distance`, the cosine *similarity*, so a higher score means more relevant, matching the
Retriever contract. Because all vectors are normalised, BGE similarities for real matches
usually land around 0.6-0.9; the absolute number matters less than the ranking.

Strength: finds passages with the same *meaning* in different words ("vacation" ~ "paid time
off"). Weakness: exact tokens with little meaning of their own (acronyms like "MVC", ticket
ids, error codes) match poorly. Phase 3's keyword + hybrid search fixes that.
"""

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.embeddings import Embedder
from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever
from models import ChunkRecord, DocumentRecord


class VectorRetriever(Retriever):
    name = "vector"

    def __init__(self, embedder: Embedder, session_factory: async_sessionmaker[AsyncSession]):
        self._embedder = embedder
        self._session_factory = session_factory

    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        query_vector = await self._embedder.embed_query(query)
        distance = ChunkRecord.embedding.cosine_distance(query_vector)
        statement = (
            select(ChunkRecord, DocumentRecord, distance.label("distance"))
            .join(DocumentRecord, ChunkRecord.document_id == DocumentRecord.id)
            .where(DocumentRecord.status == "ready")
            # ORDER BY distance + LIMIT is the exact shape the HNSW index can serve.
            .order_by(distance)
            .limit(top_k)
        )
        statement = apply_filters(statement, filters)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [
            to_chunk(chunk, document, score=round(1 - float(dist), 4))
            for chunk, document, dist in rows
        ]


def apply_filters(statement: Select, filters: RetrievalFilters | None) -> Select:
    """Metadata filtering: narrow the candidates with plain SQL WHERE clauses.

    Caveat worth knowing: with an HNSW index, Postgres walks the graph first and filters
    after, so a very selective filter can return fewer than top_k rows. pgvector's
    `hnsw.iterative_scan` setting addresses that if it ever bites.
    """
    if filters is None:
        return statement
    if filters.sources:
        statement = statement.where(DocumentRecord.source.in_(filters.sources))
    if filters.metadata:
        statement = statement.where(DocumentRecord.metadata_.contains(filters.metadata))
    if filters.access_tags is not None:
        statement = statement.where(DocumentRecord.access_tags.overlap(filters.access_tags))
    return statement


def to_chunk(chunk: ChunkRecord, document: DocumentRecord, *, score: float) -> Chunk:
    """Shared by every SQL-backed retriever, so all of them return identical Chunk shapes."""
    return Chunk(
        id=str(chunk.id),
        document_id=document.id,
        text=chunk.text,
        title=document.title,
        url=document.url,
        metadata={"heading": chunk.heading, "source": document.source, "ordinal": chunk.ordinal},
        score=score,
    )
