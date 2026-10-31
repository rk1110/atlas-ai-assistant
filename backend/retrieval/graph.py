"""Graph search (GraphRAG): answer relationship questions by walking the knowledge graph.

    "Who leads the team that owns the expense policy?"
      1. find entities named in the question     -> Expense Policy   (full-text match)
      2. walk up to 2 hops from them              -> Finance Team OWNS Expense Policy
                                                     Elena Petrova LEADS Finance Team
      3. group the facts by the document that states them, one source per document

Each group becomes an ordinary Chunk whose document_id is the real document, so the model
cites it and the citation chip opens it, exactly like a passage. The chunk's text is a
list of facts with the sentence each came from ("evidence").

On its own, graph search only knows relations, not policy details, and returns nothing
for questions that name no entity. That's why it's used inside hybrid search as a third
ranked list (strategy `hybrid_graph`), never alone in the chat.
"""

import logging
from collections import defaultdict

from core.interfaces.retriever import Chunk, RetrievalFilters, Retriever
from graph.schema import VERBS
from graph.store import Fact, GraphStore

logger = logging.getLogger(__name__)

# Keep entities scoring at least 75% of the best match. Lower lets generic words in, e.g.
# "team" in "who leads the team that owns the expense policy?" matching "Security Team".
SEED_SCORE_RATIO = 0.75
SEED_TYPES_SKIPPED = {"Company"}  # "Acme" matches almost every question


class GraphRetriever(Retriever):
    name = "graph"

    def __init__(self, store: GraphStore | None, *, max_facts: int = 20, hops: int = 2):
        self._store = store
        self._max_facts = max_facts
        self._hops = hops

    async def retrieve(
        self, query: str, filters: RetrievalFilters | None = None, top_k: int = 5
    ) -> list[Chunk]:
        if self._store is None:
            return []
        try:
            matches = await self._store.find_entities(query, limit=5)
            seeds = [
                m for m in matches
                if m.type not in SEED_TYPES_SKIPPED
                and m.score >= SEED_SCORE_RATIO * matches[0].score
            ][:3]  # fmt: skip
            facts = await self._store.facts_around(
                [s.key for s in seeds], hops=self._hops, limit=self._max_facts
            )
        except Exception:  # Neo4j down: answer from the other retrievers instead of failing
            logger.warning("graph search failed; continuing without it", exc_info=True)
            return []
        if filters and filters.sources:
            facts = [f for f in facts if f.document_id.split(":", 1)[0] in filters.sources]
        return facts_to_chunks(facts, [s.name for s in seeds])[:top_k]


def facts_to_chunks(facts: list[Fact], seeds: list[str]) -> list[Chunk]:
    """One chunk per source document, ranked by how close its facts are to the question."""
    by_document: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        by_document[fact.document_id].append(fact)
    ranked = sorted(
        by_document.values(), key=lambda group: (min(f.hops for f in group), -len(group))
    )
    return [
        Chunk(
            id=f"graph:{group[0].document_id}",
            document_id=group[0].document_id,
            title=group[0].document_title,
            text="\n".join(f'- {sentence(f)} ("{f.evidence}")' for f in group),
            metadata={
                "heading": "Knowledge graph",
                "source": group[0].document_id.split(":", 1)[0],
                "graph_entities": seeds,
            },
            # 1.0 for facts one hop from a question entity, 0.5 for two hops.
            score=round(1 / min(f.hops for f in group), 4),
        )
        for group in ranked
    ]


def sentence(fact: Fact) -> str:
    return f"{fact.source} {VERBS.get(fact.relation, fact.relation.lower())} {fact.target}"
