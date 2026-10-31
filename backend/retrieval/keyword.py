"""Keyword search: find chunks that contain the question's words, ranked with BM25.

    "What is an MVC at GitLab?"
        ──Postgres to_tsvector──▶ ['mvc', 'gitlab']           (stemmed, stop words gone)
        ──GIN index, 'mvc' | 'gitlab'──▶ every chunk containing either word
        ──BM25──▶ rare words count more: 'mvc' (in 4 chunks) beats 'gitlab' (in 500)

Why: vector search matches *meaning*, so it is weak on tokens with little meaning of their
own: acronyms (MVC), codes, email addresses, channel names. Keyword search matches the exact
token. The two fail in different places, which is why hybrid search (retrieval/hybrid.py)
combines them.

Why BM25 in Python instead of Postgres' own ts_rank: ts_rank has no notion of how *rare* a
word is, so a question's common word ("gitlab", "acme") outweighs the one word that matters.
BM25 is the ranking formula behind Elasticsearch and Lucene; its IDF term is that rarity.
Postgres still does the heavy lifting (stemming, stop words, the indexed candidate lookup),
and every number BM25 needs comes from the candidate rows, so there is no separate index to
keep in sync with the database.
"""

import math
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever
from models import TEXT_SEARCH_CONFIG, ChunkRecord, DocumentRecord
from retrieval.vector import apply_filters, to_chunk

# BM25's two knobs, at the values almost every search engine ships with.
K1 = 1.2  # term-frequency saturation: the 5th "mvc" in a chunk adds much less than the 1st
B = 0.75  # length normalisation: a match in a short chunk counts more than in a long one

# One lexeme in Postgres' text form of a tsvector: 'chang':5,11B (positions, optional weight).
_LEXEME = re.compile(r"'((?:[^']|'')+)':([\d,A-D]+)")


@dataclass(frozen=True)
class _Stats:
    total: int  # chunks in the searchable corpus (N)
    average_length: float  # average distinct-word count per chunk (avgdl)


class KeywordRetriever(Retriever):
    name = "keyword"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        async with self._session_factory() as session:
            terms = await _query_terms(session, query)
            if not terms:  # e.g. a question made only of stop words: "what is it?"
                return []
            stats = await _corpus_stats(session, filters)
            statement = (
                select(ChunkRecord, DocumentRecord, ChunkRecord.search_vector)
                .join(DocumentRecord, ChunkRecord.document_id == DocumentRecord.id)
                .where(
                    DocumentRecord.status == "ready",
                    # The terms are already stemmed, so the query uses the 'simple' config
                    # (no second stemming pass). `|` = OR: any word can match.
                    ChunkRecord.search_vector.op("@@")(
                        func.to_tsquery("simple", " | ".join(_quote(t) for t in terms))
                    ),
                )
            )
            rows = (await session.execute(apply_filters(statement, filters))).all()

        parsed = [(chunk, document, _term_counts(vector or "")) for chunk, document, vector in rows]
        # Document frequency (how many chunks contain each term), straight from the
        # candidates: with an OR query, every chunk containing a term is a candidate.
        frequency = {t: sum(1 for *_, counts in parsed if t in counts) for t in terms}
        scored = [
            (bm25(terms, counts, frequency, stats), chunk, document)
            for chunk, document, counts in parsed
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            to_chunk(chunk, document, score=round(score, 4))
            for score, chunk, document in scored[:top_k]
        ]


def bm25(
    terms: list[str], counts: dict[str, int], frequency: dict[str, int], stats: _Stats
) -> float:
    """Okapi BM25 for one chunk: sum over query terms of IDF x saturated term frequency.

    IDF (inverse document frequency) = log(1 + (N - n + 0.5) / (n + 0.5)), where n chunks
    contain the term. A word in 4 of 900 chunks gets ~5.3; a word in 500 of them gets ~0.6.
    """
    length = len(counts) or 1
    score = 0.0
    for term in terms:
        tf = counts.get(term, 0)
        if tf == 0:
            continue
        n = frequency[term]
        idf = math.log(1 + (stats.total - n + 0.5) / (n + 0.5))
        norm = K1 * (1 - B + B * length / stats.average_length)
        score += idf * tf * (K1 + 1) / (tf + norm)
    return score


async def _query_terms(session: AsyncSession, query: str) -> list[str]:
    """The question analysed exactly like the chunks were: same stemming, same stop words."""
    vector = await session.scalar(select(func.to_tsvector(TEXT_SEARCH_CONFIG, query)))
    return list(_term_counts(vector or ""))


async def _corpus_stats(session: AsyncSession, filters: RetrievalFilters | None) -> _Stats:
    statement = (
        select(func.count(), func.avg(func.length(ChunkRecord.search_vector)))
        .select_from(ChunkRecord)
        .join(DocumentRecord, ChunkRecord.document_id == DocumentRecord.id)
        .where(DocumentRecord.status == "ready")
    )
    total, average = (await session.execute(apply_filters(statement, filters))).one()
    return _Stats(total=total or 0, average_length=float(average or 1))


def _term_counts(vector: str) -> dict[str, int]:
    """Parse Postgres' tsvector text into {term: how many times it occurs}.

    Document length is measured as the number of *distinct* terms (Postgres' length()), a
    slight simplification of BM25's word count, used consistently for chunks and the average.
    """
    return {
        lexeme.replace("''", "'"): len(positions.split(","))
        for lexeme, positions in _LEXEME.findall(vector)
    }


def _quote(term: str) -> str:
    """Quote a term for to_tsquery, so characters like & | ! ( : in it are literal text."""
    escaped = term.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"
